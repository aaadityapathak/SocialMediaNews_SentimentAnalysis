import logging
import urllib3
from functools import lru_cache
from flask import request, jsonify
from elasticsearch import Elasticsearch
from settings import ESSettings
from base import read_from_secret, setup_logging

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
setup_logging()

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _client() -> Elasticsearch:
    """Initialize and cache the Elasticsearch client to prevent reconnect overhead."""
    cfg = read_from_secret("elastic-api-credentials", ESSettings)

    return Elasticsearch(
        cfg.host,
        api_key=cfg.api_key,
        verify_certs=False,
        ssl_show_warn=False,
        request_timeout=30,
        retry_on_timeout=True,
        max_retries=3,
    )


def get_gdelt_timeseries():
    """
    Get political timeseries data (article volume, sentiment, and map coordinates).
    """
    es = _client()

    keywords = request.args.get(
        "keywords", type=str, default='"Anthony Albanese" OR "Peter Dutton"'
    )
    start_date = request.args.get(
        "start_date", type=str, default="20240101000000"
    )
    end_date = request.args.get("end_date", type=str, default="20261231235959")
    interval = request.args.get("interval", type=str, default="week")

    query_body = {
        "size": 0,
        "query": {
            "bool": {
                "must": [
                    {
                        "multi_match": {
                            "query": keywords,
                            "fields": [
                                "GKG_PERSONS",
                                "GKG_ORGANIZATIONS",
                                "Actor1Name",
                                "Actor2Name",
                            ],
                            "type": "best_fields",
                        }
                    },
                    {
                        "range": {
                            "TrueDate": {
                                "gte": start_date,
                                "lte": end_date,
                                "format": "yyyyMMddHHmmss",
                            }
                        }
                    },
                ]
            }
        },
        "aggs": {
            "timeseries_data": {
                "date_histogram": {
                    "field": "TrueDate",
                    "calendar_interval": interval,
                    "format": "yyyy-MM-dd",
                },
                "aggs": {
                    "total_articles_published": {
                        "sum": {"field": "NumArticles"}
                    },
                    "average_sentiment_tone": {"avg": {"field": "AvgTone"}},
                    "australian_locations": {
                        "filter": {
                            "match": {"ActionGeo_Fullname": "Australia"}
                        },
                        "aggs": {
                            "top_australian_hits": {
                                "top_hits": {
                                    "size": 100,
                                    "_source": [
                                        "ActionGeo_Lat",
                                        "ActionGeo_Long",
                                        "ActionGeo_Fullname",
                                    ],
                                }
                            }
                        },
                    },
                },
            }
        },
    }

    try:
        response = es.search(index="gdelt-index", body=query_body)

        buckets = (
            response.get("aggregations", {})
            .get("timeseries_data", {})
            .get("buckets", [])
        )

        formatted_timeseries = []
        for bucket in buckets:
            articles = bucket.get("total_articles_published", {}).get(
                "value", 0
            )
            sentiment = bucket.get("average_sentiment_tone", {}).get("value")

            raw_locations = (
                bucket.get("australian_locations", {})
                .get("top_australian_hits", {})
                .get("hits", {})
                .get("hits", [])
            )
            coordinates = []

            for hit in raw_locations:
                source = hit.get("_source", {})
                lat = source.get("ActionGeo_Lat")
                lon = source.get("ActionGeo_Long")
                name = source.get("ActionGeo_Fullname")

                if lat and lon:
                    coordinates.append(
                        {
                            "lat": float(lat),
                            "lon": float(lon),
                            "location_name": name,
                        }
                    )

            formatted_timeseries.append(
                {
                    "date": bucket["key_as_string"],
                    "article_count": int(articles) if articles else 0,
                    "average_sentiment": round(sentiment, 2)
                    if sentiment is not None
                    else 0.0,
                    "locations": coordinates,
                }
            )

        return jsonify(
            {
                "filters": {
                    "keywords": keywords,
                    "start_date": start_date,
                    "end_date": end_date,
                    "interval": interval,
                    "map_filter": "Strictly Australian Coordinates",
                },
                "timeseries": formatted_timeseries,
            }
        )

    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
