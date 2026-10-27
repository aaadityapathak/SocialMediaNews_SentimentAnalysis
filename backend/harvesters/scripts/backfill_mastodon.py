"""Backfill Mastodon archives or timelines through the processing queue."""

import logging
import random
import sys
import time
from contextlib import ExitStack, closing
from datetime import UTC, datetime, timedelta
from pathlib import Path

from elasticsearch import Elasticsearch, helpers
from valkey import Valkey

_src = Path(__file__).parents[1] / "src"
if str(_src) not in sys.path:
    sys.path.append(str(_src))

from base.backfill import BackfillPublisher, mastodon_ids
from base.log import setup_logging
from elastic.settings import ESSettings
from mastodon_retrieve import (
    MastodonHarvester,
    MastodonSearchParams,
    MastodonSettings,
)
from mastodon_retrieve import schemas as sch
from valkey_settings import ValkeySettings

logger = logging.getLogger(__name__)


def _get_storage_clients():
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


def get_clients() -> tuple[MastodonHarvester, Valkey, Elasticsearch]:
    vk, es = _get_storage_clients()
    try:
        ms = MastodonHarvester(MastodonSettings())
    except Exception:
        es.close()
        vk.close()
        raise
    return ms, vk, es


def _envelope(post, provider):
    return {
        "source": "mastodon",
        "save_common_idx": True,
        "save_provider_idx": provider,
        "data": post.model_dump(mode="json"),
    }


def backfill_from_index(
    ignore_existing: bool = False,
    batch_size: int = 250,
    queue_limit: int = 15000,
    queue_wait_seconds: float = 300,
):
    # Replaying an archive requires no Mastodon credentials or network client.
    vk, es = _get_storage_clients()
    with ExitStack() as stack:
        stack.enter_context(closing(vk))
        stack.enter_context(closing(es))
        scanner = stack.enter_context(
            closing(
                helpers.scan(
                    es,
                    query={"query": {"match_all": {}}},
                    index="mastodon-idx",
                    size=batch_size,
                    scroll="15m",
                )
            )
        )

        def records():
            for record in scanner:
                parsed = sch.Status.model_validate(record["_source"])
                yield mastodon_ids(parsed), _envelope(parsed, False)

        return BackfillPublisher(
            vk,
            es,
            ignore_existing=ignore_existing,
            batch_size=batch_size,
            queue_limit=queue_limit,
            queue_wait_seconds=queue_wait_seconds,
        ).publish(records())


def backfill_from_api(
    lookback_months: int = 6,
    end_n_months_ago: int | None = None,
    ignore_existing: bool = False,
    hashtag: str | None = None,
    local: bool = True,
    random_sleep: bool = False,
    batch_size: int = 250,
    queue_limit: int = 15000,
    queue_wait_seconds: float = 300,
) -> int:
    """Replay a time window, checking both legacy numeric and URI IDs."""
    if lookback_months <= 0 or (
        end_n_months_ago is not None and end_n_months_ago < 0
    ):
        raise ValueError("Invalid lookback window")
    ms, vk, es = get_clients()
    with ExitStack() as stack:
        for client in (vk, es, ms):
            stack.enter_context(closing(client))
        end = datetime.now(UTC) - timedelta(days=(end_n_months_ago or 0) * 31)
        start = end - timedelta(days=lookback_months * 31)
        params = MastodonSearchParams(hashtag=hashtag, local=local)
        source = stack.enter_context(closing(ms.run(start, end, params=params)))

        def records():
            for record in source:
                parsed = sch.Status.model_validate(record)
                yield (
                    mastodon_ids(parsed, common=False),
                    _envelope(parsed, True),
                )
                if random_sleep:
                    time.sleep(random.random() / 4)

        return BackfillPublisher(
            vk,
            es,
            index="mastodon-idx",
            ignore_existing=ignore_existing,
            batch_size=batch_size,
            queue_limit=queue_limit,
            queue_wait_seconds=queue_wait_seconds,
        ).publish(records())


if __name__ == "__main__":
    import fire

    setup_logging(logging.INFO)
    fire.Fire(
        {"backfill-idx": backfill_from_index, "backfill-api": backfill_from_api}
    )
