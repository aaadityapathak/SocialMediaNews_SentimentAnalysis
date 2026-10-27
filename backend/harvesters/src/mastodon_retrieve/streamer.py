"""Mastodon HTTP streaming, event validation and queue delivery."""

import asyncio
import json
import logging
from contextlib import aclosing
from dataclasses import dataclass, field
from typing import AsyncIterator

import httpx
from pydantic import ValidationError
from valkey.asyncio import Valkey

from . import schemas
from .events import iter_events
from .settings import MastodonSettings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MastodonStreamer:
    settings: MastodonSettings = field(default_factory=MastodonSettings)
    status_events: set[schemas.EventType] = field(
        default_factory=lambda: {schemas.EventType.update}
    )

    async def statuses_from_event_stream(
        self, event_stream: AsyncIterator[str]
    ) -> AsyncIterator[schemas.Status | None]:
        async for event in iter_events(event_stream):
            if event is None or event[0] not in self.status_events:
                yield None
                continue
            try:
                yield schemas.Status.model_validate_json(event[1])
            except ValidationError:
                logger.warning("Ignoring malformed Mastodon status event")
                yield None

    async def __stream_elements(
        self,
        path: str,
        headers: dict[str, str],
        params: dict[str, str | int | bool] | None = None,
    ) -> AsyncIterator[schemas.Status | None]:
        url = f"{self.settings.base_url.rstrip('/')}/{path}"
        async with httpx.AsyncClient(
            headers=headers,
            timeout=self.settings.timeout_seconds,
            follow_redirects=True,
        ) as client:
            for attempt in range(self.settings.max_retries + 1):
                try:
                    async with client.stream(
                        "GET", url, params=params
                    ) as stream:
                        stream.raise_for_status()
                        async for status in self.statuses_from_event_stream(
                            stream.aiter_lines()
                        ):
                            yield status
                    return
                except (httpx.TransportError, httpx.HTTPStatusError) as exc:
                    if isinstance(exc, httpx.HTTPStatusError):
                        if exc.response.status_code not in {
                            429,
                            500,
                            502,
                            503,
                            504,
                        }:
                            raise
                    if attempt >= self.settings.max_retries:
                        raise
                    delay = min(
                        30.0, self.settings.retry_backoff_seconds * 2**attempt
                    )
                    logger.warning(
                        "Mastodon stream disconnected; retry %d", attempt + 1
                    )
                    await asyncio.sleep(delay)

    def _headers(self) -> dict[str, str]:
        headers = {"User-Agent": self.settings.user_agent}
        if self.settings.auth_token:
            headers["Authorization"] = f"Bearer {self.settings.auth_token}"
        return headers

    async def _limited_stream(
        self, path: str, params: dict, max_elements: int | None
    ) -> AsyncIterator[schemas.Status | None]:
        if max_elements is not None and max_elements <= 0:
            return
        count = 0
        async with aclosing(
            self.__stream_elements(path, self._headers(), params)
        ) as events:
            async for item in events:
                if item is not None:
                    count += 1
                yield item
                if max_elements is not None and count >= max_elements:
                    return

    async def stream_public_timeline(
        self, max_elements: int | None = None, local: bool = False
    ) -> AsyncIterator[schemas.Status | None]:
        path = "api/v1/streaming/public"
        if local:
            path += "/local"
        async with aclosing(
            self._limited_stream(path, {}, max_elements)
        ) as events:
            async for item in events:
                yield item

    async def stream_hashtag(
        self, hashtag: str, max_elements: int | None = None, local: bool = False
    ) -> AsyncIterator[schemas.Status | None]:
        path = "api/v1/streaming/hashtag"
        if local:
            path += "/local"
        params = {"tag": hashtag.lstrip("#")}
        async with aclosing(
            self._limited_stream(path, params, max_elements)
        ) as events:
            async for item in events:
                yield item

    async def stream_to_vk(
        self,
        vk: Valkey,
        vk_list: str = "social-posts-index",
        max_time: float = 120.0,
        hashtag: str | None = None,
        local: bool = True,
    ) -> int:
        """Deliver statuses with a deadline that also interrupts idle reads."""
        if max_time <= 0:
            return 0
        total = 0
        publishing = False
        stream = (
            self.stream_hashtag(hashtag, local=local)
            if hashtag
            else self.stream_public_timeline(local=local)
        )
        deadline = asyncio.timeout(max_time)
        try:
            async with deadline:
                async with aclosing(stream) as events:
                    async for doc in events:
                        if doc is None:
                            continue
                        publishing = True
                        await vk.lpush(
                            vk_list,
                            json.dumps(
                                {
                                    "source": "mastodon",
                                    "data": doc.model_dump(mode="json"),
                                }
                            ),
                        )
                        total += 1
                        publishing = False
        except TimeoutError as exc:
            if not deadline.expired():
                raise
            if publishing:
                raise TimeoutError(
                    "Mastodon deadline expired during queue delivery; "
                    "delivery is unconfirmed"
                ) from exc
        return total
