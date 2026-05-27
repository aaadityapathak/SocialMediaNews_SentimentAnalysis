import sys
import json
import time
import logging
from pathlib import Path

import httpx
import urllib3
from valkey import Valkey
from elasticsearch import Elasticsearch

_src = Path(__file__).parents[1] / "src"
if str(_src) not in sys.path:
    sys.path.append(str(_src))

from base.log import setup_logging
from bluesky.settings import BlueskySettings
from elastic.settings import ESSettings
from valkey_settings import ValkeySettings
from wait_for_queue import wait_queue

BSKY_BASE = "https://bsky.social"
SOCIAL_POSTS_INDEX = "social-posts-index"

logger = logging.getLogger(__name__)


def _create_session(
    client: httpx.Client, handle: str, app_password: str
) -> str:
    resp = client.post(
        f"{BSKY_BASE}/xrpc/com.atproto.server.createSession",
        json={"identifier": handle, "password": app_password},
    )
    resp.raise_for_status()
    jwt = resp.json().get("accessJwt")
    if not jwt:
        raise RuntimeError("No accessJwt in createSession response")
    return jwt


def _parse_uri(uri: str) -> tuple[str, str]:
    # at://did:plc:xxx/app.bsky.feed.post/rkey -> (did, rkey)
    parts = uri.split("/")
    return parts[2], parts[-1]


def _get_posts(client: httpx.Client, jwt: str, uris: list[str]) -> list[dict]:
    resp = client.get(
        f"{BSKY_BASE}/xrpc/app.bsky.feed.getPosts",
        params=[("uris", u) for u in uris],
        headers={"Authorization": f"Bearer {jwt}"},
    )
    resp.raise_for_status()
    return resp.json().get("posts", [])


def _is_english(record: dict) -> bool:
    langs = record.get("langs")
    return not langs or "en" in langs


def _normalise(post: dict) -> dict:
    author = post.get("author") or {}
    record = post.get("record") or {}
    uri = post.get("uri") or ""
    rkey = uri.rsplit("/", 1)[-1] if uri else None
    return {
        "did": author.get("did"),
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
    client: httpx.Client,
    jwt: str,
    batch: list[str],
    vk: Valkey,
    handle: str,
    app_password: str,
) -> tuple[str, int, int]:
    """Hydrate a batch of URIs and push results to queue. Returns (jwt, inserted, lang_skipped)."""
    try:
        posts = _get_posts(client, jwt, batch)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 401:
            logger.info("JWT expired, refreshing session")
            jwt = _create_session(client, handle, app_password)
            posts = _get_posts(client, jwt, batch)
        else:
            raise

    inserted = 0
    lang_skipped = 0
    for post in posts:
        record = post.get("record") or {}
        if not _is_english(record):
            lang_skipped += 1
            continue
        to_insert = {
            "source": "bluesky",
            "save_common_idx": True,
            "save_provider_idx": True,
            "data": _normalise(post),
        }
        vk.lpush(SOCIAL_POSTS_INDEX, json.dumps(to_insert))
        inserted += 1

    time.sleep(0.3)
    return jwt, inserted, lang_skipped


def hydrate(
    input_dir: str = "backend/harvesters/data/bsky-ids",
    glob: str = "*.json",
    batch_size: int = 25,
):
    setup_logging(logging.INFO)
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    bsky_settings = BlueskySettings()
    vk_settings = ValkeySettings()
    es_settings = ESSettings()

    if not bsky_settings.handle or not bsky_settings.app_password:
        raise RuntimeError(
            "BLUESKY_HANDLE and BLUESKY_APP_PASSWORD must be set"
        )

    vk = Valkey(host=vk_settings.host, port=vk_settings.port)
    es = Elasticsearch(
        es_settings.host, api_key=es_settings.api_key, verify_certs=False
    )

    input_path = Path(input_dir)
    total_inserted = 0
    total_skipped_lang = 0
    # Track URIs queued this run to avoid duplicates across files
    queued_this_run: set[str] = set()

    with httpx.Client(timeout=30) as client:
        jwt = _create_session(
            client, bsky_settings.handle, bsky_settings.app_password
        )

        for f in sorted(input_path.glob(glob)):
            try:
                uris: list[str] = json.loads(f.read_text())
            except Exception as exc:
                logger.warning("Failed to load %s: %s", f, exc)
                continue

            logger.info("Processing %s (%d URIs)", f.name, len(uris))
            pending: list[str] = []

            for uri in uris:
                if uri in queued_this_run:
                    continue
                try:
                    did, rkey = _parse_uri(uri)
                except Exception:
                    logger.warning("Cannot parse URI: %s", uri)
                    continue
                if es.exists(
                    index=SOCIAL_POSTS_INDEX, id=f"bluesky-{did}:{rkey}"
                ):
                    logger.debug("Already indexed, skipping: %s", uri)
                    continue

                pending.append(uri)

                if len(pending) >= batch_size:
                    jwt, n_ins, n_lang = _flush_batch(
                        client,
                        jwt,
                        pending,
                        vk,
                        bsky_settings.handle,
                        bsky_settings.app_password,
                    )
                    queued_this_run.update(pending)
                    pending = []
                    total_inserted += n_ins
                    total_skipped_lang += n_lang

                    if total_inserted % 500 < batch_size:
                        logger.info(
                            "Inserted %d records (lang-skipped: %d)",
                            total_inserted,
                            total_skipped_lang,
                        )
                    if vk.llen(SOCIAL_POSTS_INDEX) > 15000:
                        logger.info(
                            "Queue high-water reached, waiting for drain"
                        )
                        wait_queue(poll_interval=30, until_length=9000)

            # Flush remaining URIs from this file
            if pending:
                jwt, n_ins, n_lang = _flush_batch(
                    client,
                    jwt,
                    pending,
                    vk,
                    bsky_settings.handle,
                    bsky_settings.app_password,
                )
                queued_this_run.update(pending)
                total_inserted += n_ins
                total_skipped_lang += n_lang

            logger.info(
                "Finished %s. Running totals — inserted: %d, lang-skipped: %d",
                f.name,
                total_inserted,
                total_skipped_lang,
            )

    logger.info(
        "Done. Inserted: %d | Skipped (lang): %d",
        total_inserted,
        total_skipped_lang,
    )


if __name__ == "__main__":
    import fire

    fire.Fire({"hydrate": hydrate})
