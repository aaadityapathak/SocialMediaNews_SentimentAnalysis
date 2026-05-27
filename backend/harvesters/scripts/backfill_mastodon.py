import sys
import json
import time
import random
import logging
from pathlib import Path
from valkey import Valkey
from datetime import datetime, timedelta, UTC
from elasticsearch import Elasticsearch, helpers


# Add source dir to system path
_src = Path(__file__).parents[1] / "src"
if str(_src) not in sys.path:
    sys.path.append(str(_src))

from base.log import setup_logging
from elastic.settings import ESSettings
from valkey_settings import ValkeySettings
from mastodon_retrieve import schemas as sch
from mastodon_retrieve import (
    MastodonHarvester,
    MastodonSettings,
    MastodonSearchParams,
)

logger = logging.getLogger(__name__)


def get_clients() -> tuple[MastodonHarvester, Valkey, Elasticsearch]:
    """
    Get clients for Mastodon, Valkey and Elasticsearch.
    :return:
    """
    vk_settings = ValkeySettings()
    es_settings = ESSettings()
    ms_settings = MastodonSettings()

    vk = Valkey(host=vk_settings.host, port=vk_settings.port)
    es = Elasticsearch(
        es_settings.host, api_key=es_settings.api_key, verify_certs=False
    )
    ms = MastodonHarvester(ms_settings)
    return ms, vk, es


def backfill_from_index(ignore_existing: bool = False, batch_size: int = 250):
    """
    Backfill from index: Insert all missing records from Mastodon index into
    common index.
    :return:
    """
    ms, vk, es = get_clients()
    scanner = helpers.scan(
        es,
        query={"query": {"match_all": {}}},
        index="mastodon-idx",
        size=250,
        scroll="15m",
    )
    total_inserted = 0
    for record in scanner:
        parsed = sch.Status.model_validate(record["_source"])
        if not ignore_existing:
            exists = es.exists(
                index="social-posts-index", id=f"mastodon-{parsed.id}"
            ) or es.exists(
                index="social-posts-index", id=f"mastodon-{parsed.uri}"
            )
            if exists:
                logger.info("Record '%s' exists - skipping insert", parsed.uri)
                continue

        to_insert = {
            "source": "mastodon",
            "save_common_idx": True,
            "save_provider_idx": False,
            "data": parsed.model_dump(mode="json"),
        }
        vk.lpush("social-posts-index", json.dumps(to_insert))
        total_inserted += 1

        if total_inserted % 1000 == 0:
            time.sleep(random.random() * 20)
            logger.info(
                "Inserted %05d records. Last created at %s",
                total_inserted,
                parsed.created_at.isoformat(),
            )
    return total_inserted


def backfill_from_api(
    lookback_months: int = 6,
    end_n_months_ago: int | None = None,
    ignore_existing: bool = False,
    hashtag: str | None = None,
    local: bool = True,
    random_sleep: bool = False,
) -> int:
    """
    Backfill mastodon data from the public timeline API.
    :param lookback_months: Look back n months from end date
    :param end_n_months_ago: End the search n months ago.
    :param ignore_existing: Whether to ignore if a record exists in mastodon
        index before inserting.
    :param hashtag: search for this hashtag
    :param local:
    :param random_sleep: Sleep for up to 0.25 seconds between valkey pushes.
    :return:
    """
    ms, vk, es = get_clients()
    total_inserted = 0
    end = datetime.now(UTC)
    if end_n_months_ago:
        end -= timedelta(days=end_n_months_ago * 31)

    start = end - timedelta(days=lookback_months * 31)
    params = MastodonSearchParams(hashtag=hashtag, local=local)

    for rec in ms.run(start, end, params=params):
        parsed = sch.Status.model_validate(rec)
        if not ignore_existing:
            exists = es.exists(index="mastodon-idx", id=parsed.id) or es.exists(
                index="mastodon-idx", id=parsed.uri
            )
            if exists:
                logger.debug("Record '%s' exists - skipping insert", parsed.uri)
                continue

        to_insert = {
            "source": "mastodon",
            "save_common_idx": True,
            "save_provider_idx": True,
            "data": parsed.model_dump(mode="json"),
        }
        vk.lpush("social-posts-index", json.dumps(to_insert))
        if random_sleep:
            time.sleep(random.random() / 4.0)

        total_inserted += 1

        if total_inserted % 100 == 0:
            logger.info(
                "Inserted %05d records. Last created at %s",
                total_inserted,
                parsed.created_at.isoformat(),
            )
    return total_inserted


if __name__ == "__main__":
    import fire
    import urllib3

    # These are due to not verifying certificates for ElasticSearch.
    # We will only access it through port forward so this is fine.
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    setup_logging(logging.INFO)
    fire.Fire(
        {"backfill-idx": backfill_from_index, "backfill-api": backfill_from_api}
    )
