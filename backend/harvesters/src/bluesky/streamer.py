import json
import re
import logging
from dataclasses import dataclass, field
from typing import AsyncIterator
from datetime import timedelta, datetime, UTC

import websockets
import time
from valkey.asyncio import Valkey

from .schemas import JetStreamPost
from .settings import BlueskySettings

logger = logging.getLogger(__name__)

# Strong signals: if any of these appear, the post is very likely AU-related
STRONG_AU_KEYWORDS = [
    "australia",
    "australian",
    "aussie",
    "aussies",
    "auspol",
    "new south wales",
    "queensland",
    "south australia",
    "western australia",
    "tasmania",
    "northern territory",
    "abc australia",
    "sbs australia",
    "guardian australia",
    "the australian",
    "straya",
]

# Medium signals: AU-specific enough to accept directly, but not as strong as the group above
MEDIUM_AU_KEYWORDS = [
    "victoria state",
    "state of victoria",
    "victorian government",
    "victorian parliament",
    "nsw government",
    "nsw parliament",
    "qld government",
    "queensland government",
    "nswpol",
    "vicpol",
    "qldpol",
    "melbourne vic",
    "melbourne victoria",
    "sydney nsw",
    "brisbane qld",
    "canberra act",
    "adelaide sa",
    "perth wa",
    "hobart tas",
    "darwin nt",
    "gold coast qld",
    "gold coast queensland",
    "geelong vic",
    "geelong victoria",
    "cairns queensland",
    "wollongong nsw",
    "australian labor party",
    "teal independent",
    "pauline hanson",
    "peter dutton",
    "adam bandt",
    "penny wong",
    "jim chalmers",
    "tanya plibersek",
    "sussan ley",
    "david littleproud",
    "jacqui lambie",
    "andrew wilkie",
    "david pocock",
    "cozzielife",
]


# Weak signals: city names or ambiguous terms; require at least two weak hits if no strong/medium hit
WEAK_CITY_KEYWORDS = [
    "victoria",
    "melbourne",
    "sydney",
    "canberra",
    "adelaide",
    "brisbane",
    "perth",
    "hobart",
    "darwin",
    "geelong",
    "gold coast",
    "sunshine coast",
    "newcastle",
    "wollongong",
    "ballarat",
    "bendigo",
    "toowoomba",
    "townsville",
    "cairns",
    "launceston",
    "albanese",
    "dutton",
    "pauline hanson",
    "alp",
    "nlp",
    "labor party",
    "cost of living",
    "housing crisis",
    "cozzie",
]


def normalise_keywords(keywords: list[str] | None) -> list[str]:
    if not keywords:
        return []
    return [kw.strip().lower() for kw in keywords if kw and kw.strip()]


def contains_keyword(text: str, keyword: str) -> bool:
    text = text.lower()
    keyword = keyword.lower()

    # multi-word phrase: use normal substring match
    if " " in keyword:
        return keyword in text

    # short abbreviation: require whole word match
    return re.search(rf"\b{re.escape(keyword)}\b", text) is not None


def count_keyword_hits(text: str, keywords: list[str]) -> int:
    return sum(1 for kw in keywords if contains_keyword(text, kw))


def is_au_relevant(text: str | None) -> bool:
    """
    Broad Australia relevance filter.

    Rules:
    - any strong AU signal -> accept
    - any medium AU signal -> accept
    - otherwise require at least 2 weak city/location signals
    """
    if not isinstance(text, str) or not text.strip():
        return False

    strong_hits = count_keyword_hits(text, STRONG_AU_KEYWORDS)
    medium_hits = count_keyword_hits(text, MEDIUM_AU_KEYWORDS)
    weak_hits = count_keyword_hits(text, WEAK_CITY_KEYWORDS)

    if strong_hits >= 1:
        return True

    if medium_hits >= 1:
        return True

    if weak_hits >= 2:
        return True

    return False


def matches_topic_keywords(
    text: str | None, keywords: list[str] | None
) -> bool:
    """
    Optional second-stage topic filter.
    Example use cases:
    - transport-related terms
    - policy-related terms
    """
    if not keywords:
        return True

    if not isinstance(text, str) or not text.strip():
        return False

    lowered = text.lower()
    topic_keywords = normalise_keywords(keywords)
    return any(kw in lowered for kw in topic_keywords)


def get_matched_keywords(text: str | None, keywords: list[str]) -> list[str]:
    if not isinstance(text, str) or not text.strip():
        return []

    return [kw for kw in keywords if contains_keyword(text, kw)]


@dataclass(frozen=True)
class BlueskyStreamer:
    """
    Streamer to get live post data from Bluesky JetStream.
    """

    whitelist_ttl: timedelta = timedelta(days=7)
    settings: BlueskySettings = field(default_factory=BlueskySettings)

    async def account_whitelisted(
        self, account_handle: str, vk: Valkey
    ) -> bool:
        """
        Tell whether the current account is whitelisted, i.e. has made an Australia-relevant
        post in the last week.
        :param account_handle:
        :param vk:
        :return:
        """
        key = f"bsky:whitelist:{account_handle}"
        exists = (await vk.exists(key)) > 0
        return exists

    async def whitelist_account(self, account_handle: str, vk: Valkey):
        """
        Mark the account handle as whitelisted. Posts from this account will then
        be automatically approved without keyword checks.
        :param account_handle:
        :param vk:
        :return:
        """
        key = f"bsky:whitelist:{account_handle}"
        await vk.set(key, datetime.now(UTC).isoformat(timespec="seconds"))
        logger.info("Account whitelisted: %s", account_handle)

    async def stream_posts(
        self,
        vk: Valkey,
        max_elements: int | None = None,
        keywords: list[str] | None = None,
    ) -> AsyncIterator[JetStreamPost | None]:
        """
        Stream live Bluesky post events from JetStream.

        Args:
            vk: Valkey client
            max_elements: Maximum number of matching posts to yield.
            keywords: Optional keyword filter applied to post text.

        Yields:
            Parsed JetStreamPost objects, or None for skipped/non-post events.
        """
        url = self.settings.jetstream_url
        count = 0

        logger.info("Connecting to Bluesky JetStream: %s", url)

        async with websockets.connect(url) as websocket:
            while True:
                try:
                    message = await websocket.recv()
                    payload = json.loads(message)

                    commit = payload.get("commit", {})
                    if commit.get("collection") != "app.bsky.feed.post":
                        yield None
                        continue

                    if commit.get("operation") not in {"create", "update"}:
                        yield None
                        continue

                    post = JetStreamPost.model_validate(payload)
                    handle = post.identity.handle if post.identity else None
                    if handle:
                        # Post from whitelisted account
                        whitelisted = await self.account_whitelisted(handle, vk)
                        if whitelisted:
                            yield post
                            continue

                    # Stage 1: broad Australia filter
                    if not is_au_relevant(post.text):
                        logger.info("Post not relevant")
                        yield None
                        continue

                    # Stage 2: optional topic filter
                    if not matches_topic_keywords(post.text, keywords):
                        yield None
                        continue

                    if handle:
                        await self.whitelist_account(handle, vk)
                        logger.info("Whitelisted account")

                    yield post
                    count += 1

                    if max_elements and count >= max_elements:
                        logger.info(
                            "Reached limit (%d), stopping stream.", count
                        )
                        break

                except websockets.ConnectionClosed as exc:
                    logger.warning("JetStream connection closed: %s", exc)
                    break
                except Exception as exc:
                    logger.exception(
                        "Unexpected Bluesky streaming error: %s", exc
                    )
                    yield None

    async def stream_to_vk(
        self,
        vk: Valkey,
        queue: str = "social-posts-index",
        max_time: float = 120.0,
        keywords: list[str] | None = None,
    ) -> int:
        """
        Stream Bluesky posts to Elasticsearch for a limited time.

        AU relevance filtering is always applied.
        keywords narrows the results further.
        """
        start = time.time()
        total = 0

        async for doc in self.stream_posts(keywords=keywords, vk=vk):
            if (time.time() - start) > max_time:
                break

            if doc is None:
                continue

            document = doc.model_dump(exclude_none=True, mode="json")

            # Debug fields for Kibana / ES inspection
            text = doc.text
            document["matched_strong_keywords"] = get_matched_keywords(
                text, STRONG_AU_KEYWORDS
            )
            document["matched_medium_keywords"] = get_matched_keywords(
                text, MEDIUM_AU_KEYWORDS
            )
            document["matched_weak_keywords"] = get_matched_keywords(
                text, WEAK_CITY_KEYWORDS
            )

            if keywords:
                document["matched_topic_keywords"] = get_matched_keywords(
                    text, keywords
                )

            await vk.lpush(
                queue,
                json.dumps({"source": "bluesky", "data": document}),
            )
            total += 1

        return total
