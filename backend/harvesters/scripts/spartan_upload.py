import json
import time
import logging
from pydantic import ValidationError
from valkey import Valkey

from base import setup_logging
from elastic.settings import ESSettings
from elasticsearch import Elasticsearch
from mastodon_retrieve.schemas import Status


setup_logging()
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
    "straya"
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
    """
    Push post to the queue for indexing.
    """
    exists = es.exists(index="social-posts-index", id=f"mastodon-{post.uri}")
    if bool(exists):
        return False

    data = {"source": "mastodon", "data": post.model_dump(mode="json")}
    vk.lpush("social-posts-index", json.dumps(data))
    return True


if __name__ == "__main__":
    es_settings = ESSettings()
    vk = Valkey()
    es = Elasticsearch(
        es_settings.host,
        api_key=es_settings.api_key,
        verify_certs=False,
        ssl_show_warn=False,
    )
    file = "/home/davidstiles/ClassWork/Semester20261/COMP90024/Assignment2/comp90024_team_23/backend/harvesters/data/mastodon-large.ndjson"

    with open(file, "r", buffering=1) as f:
        indexed = 0
        discarded = 0
        failed = 0
        i = 0
        logger.info("Starting...")
        while line := f.readline():
            i += 1
            if i < 2:
                continue
            try:
                item = json.loads(line)["doc"]
                if "created_at" not in item:
                    item["created_at"] = item.pop("createdAt")
                if acct := item.get("account"):
                    if "created_at" not in acct:
                        acct["created_at"] = acct.pop("createdAt")
                if "id" not in item:
                    item["id"] = item["uri"]

                stat = Status.model_validate(item)
                txt_lower = stat.content.lower()
                keep = (
                    "mastodon.au" in stat.uri
                    or "au.social" in stat.uri
                    or (stat.tags and any(t in {tg.name for tg in stat.tags} for t in tags))
                    or any(kw in txt_lower for kw in keywords)
                    or any(tg in txt_lower for tg in tags)
                )

                if keep:
                    if index_post(stat, vk, es):
                        indexed += 1
                        time.sleep(0.033)
                else:
                    discarded += 1

                if i % 24000 == 0:
                    logger.info(
                        "Processed %d records so far. Indexed=%d, Discarded=%d, Failed=%d",
                        i,
                        indexed,
                        discarded,
                        failed,
                    )
                    logger.info("AT POSITION %d", f.tell())
                    time.sleep(10)
            except (ValidationError, KeyError) as e:
                logger.error("Failed: %s", e)
                failed += 1

        logger.info(
            "Done loading data. Totals: processed=%d, indexed=%d, discarded=%s, failed=%s",
            i,
            indexed,
            discarded,
            failed,
        )
