import logging
import time
from functools import lru_cache

from elasticsearch import Elasticsearch
from flask import jsonify, request

from base.read_fission_cfg import read_from_secret
from repositories.transport_groups import get_transport_group_counts
from settings import ESSettings

log = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _client() -> Elasticsearch:
    cfg = read_from_secret("elastic-api-credentials", ESSettings)
    return Elasticsearch(
        cfg.host,
        api_key=cfg.api_key,
        verify_certs=False,
        ssl_show_warn=False,
        request_timeout=10,
        retry_on_timeout=False,
        max_retries=0,
    )


def get_transport_groups():
    t0 = time.perf_counter()
    es = _client()
    t1 = time.perf_counter()

    platform = request.args.get("platform", type=str)
    date_from = request.args.get("from", type=str)
    date_to = request.args.get("to", type=str)

    result = get_transport_group_counts(
        es,
        platform=platform,
        date_from=date_from,
        date_to=date_to,
    )
    t2 = time.perf_counter()

    result["filters"] = {
        "platform": platform,
        "from": date_from,
        "to": date_to,
    }
    log.warning(
        "transport-groups timing client_init=%dms es_search=%dms total=%dms",
        round((t1 - t0) * 1000),
        round((t2 - t1) * 1000),
        round((t2 - t0) * 1000),
    )
    return jsonify(result)
