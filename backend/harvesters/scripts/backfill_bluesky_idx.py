import sys
import json
import time
import random
import logging
from pathlib import Path
from valkey import Valkey
from elasticsearch import Elasticsearch, helpers


# Add source dir to system path
_src = Path(__file__).parents[1] / "src"
if str(_src) not in sys.path:
    sys.path.append(str(_src))

from base.log import setup_logging
from wait_for_queue import wait_queue
from elastic.settings import ESSettings
from valkey_settings import ValkeySettings

logger = logging.getLogger(__name__)


def get_clients() -> tuple[Valkey, Elasticsearch]:
    """
    Get clients for Valkey and Elasticsearch.
    :return:
    """
    vk_settings = ValkeySettings()
    es_settings = ESSettings()

    vk = Valkey(host=vk_settings.host, port=vk_settings.port)
    es = Elasticsearch(
        es_settings.host, api_key=es_settings.api_key, verify_certs=False
    )
    return vk, es


def backfill_bsky_idx(ignore_existing: bool = False):
    """
    Backfill the social posts index from records in the bluesky index
    :param ignore_existing:
    :return:
    """
    vk, es = get_clients()
    scanner = helpers.scan(
        es,
        query={"query": {"match_all": {}}},
        index="bluesky-idx",
        size=250,
        scroll="60m",
    )
    total_inserted = 0
    for record in scanner:
        # Get document ID
        doc = record["_source"]
        did = doc.get("did")
        commit = doc.get("commit") or {}
        rkey = commit.get("rkey") or round(time.time())
        doc_id = doc.get("uri") or f"{did}:{rkey}"

        if not ignore_existing:
            exists = es.exists(
                index="social-posts-index", id=f"bluesky-{doc_id}"
            )
            if exists:
                logger.info("Record '%s' exists - skipping insert", doc_id)
                continue

        to_insert = {
            "source": "bluesky",
            "save_common_idx": True,
            "save_provider_idx": False,
            "data": doc,
        }
        vk.lpush("social-posts-index", json.dumps(to_insert))
        total_inserted += 1

        if total_inserted % 1000 == 0:
            logger.info(
                "Inserted %05d records.",
                total_inserted,
            )
            # Give some time for processors to handle the queue
            time.sleep(random.random() * 30)
    return total_inserted


def backfill_bluesky_historical(
    source_index: str = "bluesky-historical-idx", ignore_existing: bool = False
):
    """
    Do a backfill from a historical Bluesky Index (with large amounts of data)
    :param source_index:
    :param ignore_existing:
    :return:
    """
    vk, es = get_clients()
    scanner = helpers.scan(
        es,
        query={"query": {"match_all": {}}},
        index=source_index,
        size=250,
        scroll="120m",
    )
    total_inserted = 0
    for record in scanner:
        # Get document ID
        doc = record["_source"]
        did = doc.get("did")
        commit = doc.get("commit") or {}
        rkey = commit.get("rkey") or round(time.time())
        doc_id = doc.get("uri") or f"{did}:{rkey}"

        if not ignore_existing:
            exists = es.exists(
                index="social-posts-index", id=f"bluesky-{doc_id}"
            )
            if exists:
                logger.info("Record '%s' exists - skipping insert", doc_id)
                continue

        to_insert = {
            "source": "bluesky",
            "save_common_idx": True,
            "save_provider_idx": True,
            "data": doc,
        }
        vk.lpush("social-posts-index", json.dumps(to_insert))
        total_inserted += 1
        time.sleep(0.02)

        if total_inserted % 2500 == 0:
            logger.info(
                "Inserted %05d records.",
                total_inserted,
            )
            # Give some time for processors to handle the queue
            if vk.llen("social-posts-index") < 15000:
                time.sleep(75)
            else:
                wait_queue(poll_interval=30, until_length=10000)
    return total_inserted


if __name__ == "__main__":
    import fire
    import urllib3

    # These are due to not verifying certificates for ElasticSearch.
    # We will only access it through port forward so this is fine.
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    setup_logging(logging.INFO)
    fire.Fire(
        {
            "sync-index": backfill_bsky_idx,
            "historical": backfill_bluesky_historical,
        }
    )
