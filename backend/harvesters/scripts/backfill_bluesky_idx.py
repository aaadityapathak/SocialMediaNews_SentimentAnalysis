"""Backfill existing Bluesky indices into the processing queue."""

import logging
import sys
from contextlib import ExitStack, closing
from pathlib import Path

from elasticsearch import Elasticsearch, helpers
from valkey import Valkey

_src = Path(__file__).parents[1] / "src"
if str(_src) not in sys.path:
    sys.path.append(str(_src))

from base.backfill import BackfillPublisher, bluesky_ids
from base.log import setup_logging
from elastic.settings import ESSettings
from valkey_settings import ValkeySettings

logger = logging.getLogger(__name__)


def get_clients() -> tuple[Valkey, Elasticsearch]:
    vk_settings, es_settings = ValkeySettings(), ESSettings()
    vk = Valkey(
        host=vk_settings.host,
        port=vk_settings.port,
        socket_timeout=30,
        socket_connect_timeout=30,
    )
    try:
        es = Elasticsearch(
            es_settings.host,
            api_key=es_settings.api_key,
            verify_certs=False,
            request_timeout=30,
        )
    except Exception:
        vk.close()
        raise
    return vk, es


def _backfill(
    source_index,
    save_provider_idx,
    ignore_existing,
    batch_size,
    queue_limit,
    queue_wait_seconds,
):
    vk, es = get_clients()
    with ExitStack() as stack:
        stack.enter_context(closing(vk))
        stack.enter_context(closing(es))
        scanner = stack.enter_context(
            closing(
                helpers.scan(
                    es,
                    query={"query": {"match_all": {}}},
                    index=source_index,
                    size=batch_size,
                    scroll="15m",
                )
            )
        )

        def records():
            for record in scanner:
                doc = record["_source"]
                yield (
                    bluesky_ids(doc),
                    {
                        "source": "bluesky",
                        "save_common_idx": True,
                        "save_provider_idx": save_provider_idx,
                        "data": doc,
                    },
                )

        publisher = BackfillPublisher(
            vk,
            es,
            ignore_existing=ignore_existing,
            batch_size=batch_size,
            queue_limit=queue_limit,
            queue_wait_seconds=queue_wait_seconds,
        )
        total = publisher.publish(records())
        logger.info("Queued %d Bluesky records from %s", total, source_index)
        return total


def backfill_bsky_idx(
    ignore_existing: bool = False,
    batch_size: int = 250,
    queue_limit: int = 15000,
    queue_wait_seconds: float = 300,
):
    return _backfill(
        "bluesky-idx",
        False,
        ignore_existing,
        batch_size,
        queue_limit,
        queue_wait_seconds,
    )


def backfill_bluesky_historical(
    source_index: str = "bluesky-historical-idx",
    ignore_existing: bool = False,
    batch_size: int = 250,
    queue_limit: int = 15000,
    queue_wait_seconds: float = 300,
):
    return _backfill(
        source_index,
        True,
        ignore_existing,
        batch_size,
        queue_limit,
        queue_wait_seconds,
    )


if __name__ == "__main__":
    import fire

    setup_logging(logging.INFO)
    fire.Fire(
        {
            "sync-index": backfill_bsky_idx,
            "historical": backfill_bluesky_historical,
        }
    )
