"""Hydrate Bluesky URI lists with bounded API and queue batches."""

import json
import logging
import sys
import time
from collections import OrderedDict
from contextlib import ExitStack, closing
from itertools import batched
from pathlib import Path

import httpx
from elasticsearch import Elasticsearch
from valkey import Valkey

_src = Path(__file__).parents[1] / "src"
if str(_src) not in sys.path:
    sys.path.append(str(_src))

from base.backfill import (
    bluesky_ids,
    existing_ids,
    parse_bluesky_uri,
    wait_for_capacity,
)
from base.log import setup_logging
from bluesky.settings import BlueskySettings
from elastic.settings import ESSettings
from valkey_settings import ValkeySettings

BSKY_BASE = "https://bsky.social"
SOCIAL_POSTS_INDEX = "social-posts-index"
logger = logging.getLogger(__name__)


def _create_session(
    client: httpx.Client, handle: str, app_password: str
) -> str:
    response = client.post(
        f"{BSKY_BASE}/xrpc/com.atproto.server.createSession",
        json={"identifier": handle, "password": app_password},
    )
    response.raise_for_status()
    jwt = response.json().get("accessJwt")
    if not jwt:
        raise RuntimeError("No accessJwt in createSession response")
    return jwt


def _parse_uri(uri: str) -> tuple[str, str]:
    return parse_bluesky_uri(uri)


def _get_posts(client: httpx.Client, jwt: str, uris: list[str]) -> list[dict]:
    if not 1 <= len(uris) <= 25:
        raise ValueError("getPosts requires 1 to 25 URIs")
    for attempt in range(4):
        try:
            response = client.get(
                f"{BSKY_BASE}/xrpc/app.bsky.feed.getPosts",
                params=[("uris", uri) for uri in uris],
                headers={"Authorization": f"Bearer {jwt}"},
            )
            response.raise_for_status()
            return response.json().get("posts", [])
        except (httpx.TransportError, httpx.HTTPStatusError) as error:
            retryable = isinstance(
                error, httpx.TransportError
            ) or error.response.status_code in {429, 500, 502, 503, 504}
            if not retryable or attempt == 3:
                raise
            delay = 2**attempt
            if isinstance(error, httpx.HTTPStatusError):
                try:
                    delay = min(
                        30,
                        max(
                            0,
                            float(
                                error.response.headers.get("Retry-After", delay)
                            ),
                        ),
                    )
                except ValueError:
                    pass
            time.sleep(delay)
    raise RuntimeError("Unreachable retry state")


def _is_english(record: dict) -> bool:
    languages = record.get("langs")
    return not languages or "en" in languages


def _normalise(post: dict) -> dict:
    did, rkey = _parse_uri(post["uri"])
    author, record = post.get("author") or {}, post.get("record") or {}
    # Retain the historical DID:key processor identity; the URI alias is only
    # used for existence checks, so existing document IDs do not change.
    return {
        "did": did,
        "kind": "hydrate",
        "identity": {"handle": author.get("handle")},
        "commit": {
            "operation": "create",
            "collection": "app.bsky.feed.post",
            "rkey": rkey,
            "cid": post.get("cid"),
            "record": {
                "text": record.get("text"),
                "createdAt": record.get("createdAt"),
                "langs": record.get("langs"),
            },
        },
        "matched_strong_keywords": [],
        "matched_medium_keywords": [],
        "matched_weak_keywords": [],
        "matched_topic_keywords": [],
    }


def _flush_batch(
    client,
    jwt,
    batch,
    vk,
    handle,
    app_password,
    queue_limit=15000,
    queue_wait_seconds=300,
):
    """Hydrate a batch, refreshing an expired session once."""
    try:
        posts = _get_posts(client, jwt, batch)
    except httpx.HTTPStatusError as error:
        if error.response.status_code != 401:
            raise
        jwt = _create_session(client, handle, app_password)
        posts = _get_posts(client, jwt, batch)
    messages, lang_skipped = [], 0
    seen = set()
    requested = set(batch)
    for post in posts:
        uri = post.get("uri")
        if uri not in requested or uri in seen:
            continue
        seen.add(uri)
        if not _is_english(post.get("record") or {}):
            lang_skipped += 1
            continue
        messages.append(
            json.dumps(
                {
                    "source": "bluesky",
                    "save_common_idx": True,
                    "save_provider_idx": True,
                    "data": _normalise(post),
                }
            )
        )
    if messages:
        wait_for_capacity(
            vk,
            max_queue_length=queue_limit,
            pending=len(messages),
            timeout=queue_wait_seconds,
        )
        vk.lpush(SOCIAL_POSTS_INDEX, *messages)
    return jwt, len(messages), lang_skipped


def _iter_uris(path: Path):
    """Stream NDJSON; bound legacy JSON arrays to 64 MiB per file."""
    if path.suffix.lower() in {".jsonl", ".ndjson"}:
        with path.open(encoding="utf-8") as source:
            for line in source:
                if line.strip():
                    yield json.loads(line)
    else:
        if path.stat().st_size > 64 * 1024 * 1024:
            raise ValueError(
                "URI JSON files over 64 MiB must be split or converted to NDJSON"
            )
        uris = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(uris, list):
            raise ValueError("Expected a JSON array of Bluesky URIs")
        yield from uris


def hydrate(
    input_dir: str = "backend/harvesters/data/bsky-ids",
    glob: str = "*.json",
    batch_size: int = 25,
    queue_limit: int = 15000,
    queue_wait_seconds: float = 300,
    recent_ids_limit: int = 20000,
):
    if (
        not 1 <= batch_size <= 25
        or queue_limit < batch_size
        or queue_wait_seconds < 0
        or recent_ids_limit < 1
    ):
        raise ValueError("Invalid hydration batch, queue, or cache settings")
    input_path = Path(input_dir)
    if not input_path.is_dir():
        raise FileNotFoundError(input_path)
    setup_logging(logging.INFO)
    bsky, vk_settings, es_settings = (
        BlueskySettings(),
        ValkeySettings(),
        ESSettings(),
    )
    if not bsky.handle or not bsky.app_password:
        raise RuntimeError(
            "BLUESKY_HANDLE and BLUESKY_APP_PASSWORD must be set"
        )
    total_inserted, total_skipped_lang = 0, 0
    recent = OrderedDict()
    with ExitStack() as stack:
        vk = stack.enter_context(
            closing(
                Valkey(
                    host=vk_settings.host,
                    port=vk_settings.port,
                    socket_timeout=30,
                    socket_connect_timeout=30,
                )
            )
        )
        es = stack.enter_context(
            closing(
                Elasticsearch(
                    es_settings.host,
                    api_key=es_settings.api_key,
                    verify_certs=False,
                    request_timeout=30,
                )
            )
        )
        client = stack.enter_context(httpx.Client(timeout=30))
        jwt = _create_session(client, bsky.handle, bsky.app_password)
        for path in sorted(input_path.glob(glob)):
            for batch in batched(_iter_uris(path), batch_size):
                candidates = {}
                for uri in batch:
                    try:
                        _parse_uri(uri)
                    except (ValueError, TypeError):
                        logger.warning("Skipping malformed Bluesky URI")
                        continue
                    if uri not in recent:
                        candidates[uri] = bluesky_ids({"uri": uri})
                found = existing_ids(
                    es,
                    SOCIAL_POSTS_INDEX,
                    (
                        ident
                        for aliases in candidates.values()
                        for ident in aliases
                    ),
                )
                pending = [
                    uri
                    for uri, aliases in candidates.items()
                    if not found.intersection(aliases)
                ]
                if pending:
                    jwt, inserted, skipped = _flush_batch(
                        client,
                        jwt,
                        pending,
                        vk,
                        bsky.handle,
                        bsky.app_password,
                        queue_limit,
                        queue_wait_seconds,
                    )
                    total_inserted += inserted
                    total_skipped_lang += skipped
                for uri in candidates:
                    recent[uri] = None
                    recent.move_to_end(uri)
                    if len(recent) > recent_ids_limit:
                        recent.popitem(last=False)
            logger.info(
                "Processed %s: queued=%d, language-skipped=%d",
                path.name,
                total_inserted,
                total_skipped_lang,
            )
    return {"inserted": total_inserted, "skipped_language": total_skipped_lang}


if __name__ == "__main__":
    import fire

    fire.Fire({"hydrate": hydrate})
