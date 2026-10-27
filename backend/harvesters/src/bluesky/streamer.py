"""Bounded JetStream ingestion and queue delivery."""

import asyncio
import json
import logging
from contextlib import aclosing
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import AsyncIterator
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import websockets
from pydantic import ValidationError
from valkey.asyncio import Valkey

from .filters import (  # Re-export the existing filter API.
    MEDIUM_AU_KEYWORDS,
    STRONG_AU_KEYWORDS,
    WEAK_CITY_KEYWORDS,
    contains_keyword as contains_keyword,
    count_keyword_hits as count_keyword_hits,
    get_matched_keywords,
    is_au_relevant,
    matches_topic_keywords,
    normalise_keywords,
)
from .schemas import JetStreamPost
from .settings import BlueskySettings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BlueskyStreamer:
    """Stream post events with bounded reconnects and optional topic filtering."""

    whitelist_ttl: timedelta = timedelta(days=7)
    settings: BlueskySettings = field(default_factory=BlueskySettings)

    async def account_whitelisted(
        self, account_handle: str, vk: Valkey
    ) -> bool:
        return (await vk.exists(f"bsky:whitelist:{account_handle}")) > 0

    async def whitelist_account(self, account_handle: str, vk: Valkey):
        await vk.set(
            f"bsky:whitelist:{account_handle}",
            datetime.now(UTC).isoformat(timespec="seconds"),
            ex=self.whitelist_ttl,
        )

    async def stream_posts(
        self,
        vk: Valkey,
        max_elements: int | None = None,
        keywords: list[str] | None = None,
    ) -> AsyncIterator[JetStreamPost | None]:
        """Yield matching posts; malformed/non-post events yield ``None``.

        JetStream commit events normally contain a DID but no identity handle.
        Use the stable DID for the relevance whitelist. A whitelist only bypasses
        the Australia filter; requested topics and limits always apply.
        """
        if max_elements is not None and max_elements <= 0:
            return
        count = 0
        retries = 0
        cursor = None
        keywords = normalise_keywords(keywords)
        while True:
            url = self.settings.jetstream_url
            if cursor is not None:
                parts = urlsplit(url)
                query = [
                    (k, v) for k, v in parse_qsl(parts.query) if k != "cursor"
                ]
                query.append(("cursor", str(cursor)))
                url = urlunsplit(parts._replace(query=urlencode(query)))
            try:
                async with websockets.connect(url) as websocket:
                    while True:
                        message = await websocket.recv()
                        try:
                            post = JetStreamPost.model_validate_json(message)
                        except (ValidationError, ValueError, TypeError):
                            logger.warning("Ignoring malformed JetStream event")
                            yield None
                            continue
                        commit = post.commit
                        if post.time_us is not None:
                            cursor = post.time_us
                        if (
                            not commit
                            or commit.collection != "app.bsky.feed.post"
                            or commit.operation not in {"create", "update"}
                            or not post.did
                            or not commit.rkey
                            or not post.text
                        ):
                            yield None
                            continue
                        if not matches_topic_keywords(post.text, keywords):
                            yield None
                            continue
                        account = post.did
                        # Most posts are rejected locally, avoiding a Valkey lookup
                        # for each relevant event and reusing the stable account ID.
                        relevant = is_au_relevant(post.text)
                        if not relevant and not await self.account_whitelisted(
                            account, vk
                        ):
                            yield None
                            continue
                        if relevant:
                            await self.whitelist_account(account, vk)
                        count += 1
                        yield post
                        if max_elements is not None and count >= max_elements:
                            return
            except (websockets.ConnectionClosed, OSError, TimeoutError):
                if retries >= self.settings.max_retries:
                    raise
                delay = min(
                    30.0, self.settings.retry_backoff_seconds * 2**retries
                )
                retries += 1
                logger.warning("JetStream disconnected; retry %d", retries)
                await asyncio.sleep(delay)

    async def stream_to_vk(
        self,
        vk: Valkey,
        queue: str = "social-posts-index",
        max_time: float = 120.0,
        keywords: list[str] | None = None,
    ) -> int:
        """Queue posts until the deadline, including when the stream is idle."""
        if max_time <= 0:
            return 0
        total = 0
        publishing = False
        deadline = asyncio.timeout(max_time)
        try:
            async with deadline:
                async with aclosing(
                    self.stream_posts(
                        keywords=keywords,
                        vk=vk,
                        max_elements=self.settings.max_posts,
                    )
                ) as posts:
                    async for doc in posts:
                        if doc is None:
                            continue
                        document = doc.model_dump(
                            exclude_none=True, mode="json"
                        )
                        for name, terms in (
                            ("strong", STRONG_AU_KEYWORDS),
                            ("medium", MEDIUM_AU_KEYWORDS),
                            ("weak", WEAK_CITY_KEYWORDS),
                        ):
                            document[f"matched_{name}_keywords"] = (
                                get_matched_keywords(doc.text, terms)
                            )
                        if keywords:
                            document["matched_topic_keywords"] = (
                                get_matched_keywords(doc.text, keywords)
                            )
                        publishing = True
                        await vk.lpush(
                            queue,
                            json.dumps({"source": "bluesky", "data": document}),
                        )
                        total += 1
                        publishing = False
        except TimeoutError as exc:
            if not deadline.expired():
                raise
            if publishing:
                raise TimeoutError(
                    "Bluesky deadline expired during queue delivery; "
                    "delivery is unconfirmed"
                ) from exc
        return total
