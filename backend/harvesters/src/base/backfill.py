"""Bounded deduplication, existence checks, and publication for backfills."""

import json
import time
from collections import OrderedDict
from collections.abc import Iterable
from itertools import batched

QUEUE_NAME = "social-posts-index"


def parse_bluesky_uri(uri: str) -> tuple[str, str]:
    if not isinstance(uri, str):
        raise TypeError("Bluesky URI must be a string")
    parts = uri.split("/")
    if (
        len(parts) != 5
        or parts[:2] != ["at:", ""]
        or not parts[2].startswith("did:")
        or parts[3] != "app.bsky.feed.post"
        or not parts[4]
    ):
        raise ValueError("Expected an at:// DID post URI")
    return parts[2], parts[4]


def bluesky_ids(doc: dict) -> tuple[str, ...]:
    """Check both historical URI and DID:key identities without rewriting data."""
    uri = doc.get("uri")
    did = doc.get("did")
    rkey = (doc.get("commit") or {}).get("rkey")
    if uri:
        uri_did, uri_key = parse_bluesky_uri(uri)
        did, rkey = did or uri_did, rkey or uri_key
    if not did or not rkey:
        raise ValueError("Bluesky post requires a stable URI or DID and key")
    aliases = [f"bluesky-{did}:{rkey}"]
    aliases.append(f"bluesky-{uri or f'at://{did}/app.bsky.feed.post/{rkey}'}")
    return tuple(dict.fromkeys(aliases))


def mastodon_ids(post, *, common: bool = True) -> tuple[str, ...]:
    prefix = "mastodon-" if common else ""
    return tuple(
        dict.fromkeys(f"{prefix}{ident}" for ident in (post.uri, post.id))
    )


def existing_ids(es, index: str, ids: Iterable[str]) -> set[str]:
    requested = list(dict.fromkeys(ids))
    if not requested:
        return set()
    response = es.mget(index=index, ids=requested, source=False)
    documents = response.get("docs", [])
    if (
        len(documents) != len(requested)
        or any("error" in item for item in documents)
        or {item.get("_id") for item in documents} != set(requested)
    ):
        raise RuntimeError("Incomplete Elasticsearch existence check")
    return {item["_id"] for item in documents if item.get("found", False)}


def wait_for_capacity(
    vk,
    *,
    queue: str = QUEUE_NAME,
    max_queue_length: int = 15000,
    pending: int = 0,
    timeout: float = 300,
    poll_interval: float = 1,
    on_poll=None,
) -> None:
    """Wait for queue capacity, raising if processors stop draining it."""
    if (
        max_queue_length < pending
        or pending < 0
        or timeout < 0
        or poll_interval <= 0
    ):
        raise ValueError("Invalid queue capacity or wait settings")
    deadline = time.monotonic() + timeout
    while True:
        length = vk.llen(queue)
        if on_poll is not None:
            on_poll(length)
        if length + pending <= max_queue_length:
            return
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError(
                f"Queue {queue!r} did not drain within {timeout}s"
            )
        time.sleep(min(poll_interval, remaining))


class BackfillPublisher:
    """Publish (identity aliases, queue envelope) records in bounded batches.

    Elasticsearch checks are per batch. The first alias is the canonical
    identity used to prevent repeat queue writes before indexing completes.
    Legacy numeric Mastodon aliases are checked but are not globally unique.
    """

    def __init__(
        self,
        vk,
        es,
        *,
        index: str = QUEUE_NAME,
        batch_size: int = 250,
        ignore_existing: bool = False,
        queue_limit: int = 15000,
        queue_wait_seconds: float = 300,
        recent_ids_limit: int = 20000,
    ):
        if not 1 <= batch_size <= 1000:
            raise ValueError("batch_size must be between 1 and 1000")
        if (
            queue_limit < batch_size
            or queue_wait_seconds < 0
            or recent_ids_limit < 1
        ):
            raise ValueError("Invalid backfill queue/cache settings")
        self.vk, self.es = vk, es
        self.index = index
        self.batch_size = batch_size
        self.ignore_existing = ignore_existing
        self.queue_limit = queue_limit
        self.queue_wait_seconds = queue_wait_seconds
        self.recent_ids_limit = recent_ids_limit
        self.recent = OrderedDict()

    def publish(self, records: Iterable[tuple[tuple[str, ...], dict]]) -> int:
        total = 0
        for batch in batched(records, self.batch_size):
            unique = []
            seen = set()
            identities = set()
            for aliases, payload in batch:
                if not aliases or any(not ident for ident in aliases):
                    raise ValueError("Backfill records require stable IDs")
                canonical = aliases[0]
                if canonical in identities or canonical in self.recent:
                    continue
                identities.add(canonical)
                seen.update(aliases)
                unique.append((aliases, payload))
            found = (
                set()
                if self.ignore_existing
                else existing_ids(self.es, self.index, seen)
            )
            pending = [
                (ids, payload)
                for ids, payload in unique
                if not found.intersection(ids)
            ]
            if pending:
                messages = [json.dumps(payload) for _, payload in pending]
                wait_for_capacity(
                    self.vk,
                    pending=len(messages),
                    max_queue_length=self.queue_limit,
                    timeout=self.queue_wait_seconds,
                )
                self.vk.lpush(QUEUE_NAME, *messages)
                total += len(messages)
            # Remember only after the batch has been acknowledged by Valkey.
            for aliases, _ in unique:
                canonical = aliases[0]
                self.recent[canonical] = None
                self.recent.move_to_end(canonical)
                if len(self.recent) > self.recent_ids_limit:
                    self.recent.popitem(last=False)
        return total
