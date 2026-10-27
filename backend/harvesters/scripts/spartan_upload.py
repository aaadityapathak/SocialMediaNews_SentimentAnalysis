import json
import logging
import sys
from contextlib import ExitStack, closing
from pathlib import Path

from pydantic import ValidationError
from valkey import Valkey

_src = Path(__file__).parents[1] / "src"
if str(_src) not in sys.path:
    sys.path.append(str(_src))

from base import setup_logging
from base.backfill import BackfillPublisher, mastodon_ids
from elastic.settings import ESSettings
from elasticsearch import Elasticsearch
from mastodon_retrieve.schemas import Status
from valkey_settings import ValkeySettings

logger = logging.getLogger(__name__)

tags = [
    "auspol",
    "ausvotes",
    "ausvotes25",
    "australiaelection",
    "federalelection",
    "cozzielife",
    "cozzie",
    "australia",
    "victoria",
    "melbourne",
    "canberra",
    "nsw",
    "vicpol",
    "aussie",
    "queensland",
    "tasmania",
    "straya",
]

keywords = [
    "auspol",
    "ausvotes",
    "australia",
    "australian government",
    "australia voting",
    "australian elections",
    "australian politics",
    "australian federal election",
    "election day australia",
    "labor party",
    "labor party",
    "liberal party australia",
    "australian greens",
    "nationals australia",
    "one nation party",
    "teal independent",
    "anthony albanese",
    "peter dutton",
    "adam bandt",
    "jim chalmers",
    "sussan ley",
    "pauline hanson",
    "cost of living australia",
    "housing australia",
    "barnaby joyce",
    "cozzie",
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


def index_post(post: Status, vk: Valkey, es: Elasticsearch) -> bool:
    """Compatibility wrapper; bulk uploads use one publisher across batches."""
    data = {"source": "mastodon", "data": post.model_dump(mode="json")}
    return bool(
        BackfillPublisher(vk, es, batch_size=1).publish(
            [(mastodon_ids(post), data)]
        )
    )


def _keep(post: Status) -> bool:
    text = post.content.lower()
    post_tags = {tag.name.lower() for tag in post.tags or []}
    return (
        "mastodon.au" in post.uri
        or "au.social" in post.uri
        or bool(post_tags.intersection(tags))
        or any(keyword in text for keyword in keywords)
        or any(tag in text for tag in tags)
    )


def _records(path: Path, counts: dict):
    with path.open(encoding="utf-8") as source:
        for line in source:
            if not line.strip():
                continue
            counts["processed"] += 1
            try:
                item = json.loads(line)
                item = item.get("doc", item)
                if "created_at" not in item:
                    item["created_at"] = item.pop("createdAt")
                if (acct := item.get("account")) and "created_at" not in acct:
                    acct["created_at"] = acct.pop("createdAt")
                if "id" not in item:
                    item["id"] = item["uri"]
                post = Status.model_validate(item)
            except (
                ValidationError,
                KeyError,
                ValueError,
                TypeError,
                AttributeError,
            ):
                counts["failed"] += 1
                logger.warning(
                    "Skipping malformed record %d", counts["processed"]
                )
                continue
            if not _keep(post):
                counts["discarded"] += 1
                continue
            yield (
                mastodon_ids(post),
                {"source": "mastodon", "data": post.model_dump(mode="json")},
            )


def upload(
    file: str,
    batch_size: int = 250,
    queue_limit: int = 15000,
    queue_wait_seconds: float = 300,
    ignore_existing: bool = False,
):
    """Stream a supplied Mastodon NDJSON file into the processing queue."""
    path = Path(file)
    if not path.is_file():
        raise FileNotFoundError(path)
    setup_logging()
    es_settings, vk_settings = ESSettings(), ValkeySettings()
    counts = {"processed": 0, "indexed": 0, "discarded": 0, "failed": 0}
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
        records = stack.enter_context(closing(_records(path, counts)))
        counts["indexed"] = BackfillPublisher(
            vk,
            es,
            batch_size=batch_size,
            queue_limit=queue_limit,
            queue_wait_seconds=queue_wait_seconds,
            ignore_existing=ignore_existing,
        ).publish(records)
    logger.info("Done loading data: %s", counts)
    return counts


if __name__ == "__main__":
    import fire

    fire.Fire(upload)
