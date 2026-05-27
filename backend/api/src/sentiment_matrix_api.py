import logging
from functools import lru_cache
from elasticsearch import Elasticsearch
from flask import jsonify, request

from base.read_fission_cfg import read_from_secret
from repositories.sentiment_matrix import get_transport_sentiment_matrix
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


def get_transport_sentiment():
    es = _client()
    platform = request.args.get("platform", type=str)
    date_from = request.args.get("from", type=str)
    date_to = request.args.get("to", type=str)
    year = request.args.get("year", type=int)

    if year and not date_from and not date_to:
        date_from = f"{year}-01-01"
        date_to = f"{year}-12-31"

    try:
        result = get_transport_sentiment_matrix(
            es,
            platform=platform,
            date_from=date_from,
            date_to=date_to,
        )
    except Exception as exc:
        log.exception("transport-sentiment failed: %s", exc)
        raise

    result["filters"] = {
        "platform": platform,
        "from": date_from,
        "to": date_to,
        "year": year,
    }
    return jsonify(result)
