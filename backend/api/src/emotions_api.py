import logging
from flask import request
from pydantic import ValidationError
from elasticsearch import Elasticsearch

from settings import ESSettings
from api_schemas import TrendsRequest
from base import setup_logging, read_from_secret
from time_series import (
    get_sentiment_timeseries,
    get_emotions_timeseries,
    get_pct_mentions_timeseries,
)

setup_logging()

logger = logging.getLogger(__name__)


def compute_trends():
    """
    Get the trends computed for the given keywords and time range
    :return:
    """
    try:
        es_settings = read_from_secret("elastic-api-credentials", ESSettings)
        es = Elasticsearch(
            es_settings.host, api_key=es_settings.api_key, verify_certs=False
        )
        trend_type = request.headers.get("X-Fission-Params-Trend")
        body = TrendsRequest.model_validate_json(request.data)
        if trend_type == "sentiment":
            output = get_sentiment_timeseries(body, es)
        elif trend_type == "emotion":
            output = get_emotions_timeseries(body, es)
        elif trend_type == "count-proportion":
            output = get_pct_mentions_timeseries(body, es)
        else:
            return (
                "Invalid trend type. Expected 'sentiment', 'count-proportion', or 'emotion'",
                422,
            )

        return output, 200

    except ValidationError as e:
        logger.error("Invalid parameters received: %s", e)
        return "Invalid data passed", 422
    except Exception as e:
        logger.error(
            "Failed to perform aggregates: [%s.%s] %s",
            type(e).__module__,
            type(e).__name__,
            str(e),
        )
        return "Server error", 500
