from typing import Any
from elasticsearch import Elasticsearch

from constants.indexes import SOCIAL_POSTS_INDEX
from constants.sentiment_levels import SentimentLevels
from constants.transport_modes import TransportModes


def _base_filters(
    platform: str | None,
    date_from: str | None,
    date_to: str | None,
) -> list[dict]:
    filters: list[dict] = [{"exists": {"field": "text"}}]
    if platform:
        filters.append({"term": {"platform": platform}})
    if date_from or date_to:
        range: dict[str, str] = {}
        if date_from:
            range["gte"] = date_from
        if date_to:
            range["lte"] = date_to
        filters.append({"range": {"created_at": range}})
    return filters


def _get_filters(queries: dict[str, str]) -> dict[str, dict]:
    return {
        name: {
            "simple_query_string": {
                "query": query,
                "fields": ["text"],
                "default_operator": "or",
            }
        }
        for name, query in queries.items()
    }


def get_transport_sentiment_matrix(
    es: Elasticsearch,
    *,
    platform: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "size": 0,
        "track_total_hits": True,
        "query": {
            "bool": {"filter": _base_filters(platform, date_from, date_to)}
        },
        "aggs": {
            "modes": {
                "filters": {
                    "filters": _get_filters(TransportModes.as_queries())
                },
                "aggs": {
                    "sentiments": {
                        "filters": {
                            "filters": _get_filters(
                                SentimentLevels.as_queries()
                            ),
                        }
                    }
                },
            }
        },
    }

    result = es.search(
        index=SOCIAL_POSTS_INDEX,
        body=body,
        request_cache=True,
        request_timeout=20,
        preference="_local",
    )

    total_hits = result["hits"]["total"]
    total_posts = total_hits["value"]
    total_posts_is_exact = total_hits.get("relation") == "eq"

    modes_buckets = result["aggregations"]["modes"]["buckets"]
    matrix: list[dict[str, Any]] = []
    for mode in TransportModes.names():
        mode_bucket = modes_buckets[mode]
        mode_total = mode_bucket["doc_count"]
        sentiments_buckets = mode_bucket["sentiments"]["buckets"]

        row = []
        for sentiment in SentimentLevels.names():
            count = sentiments_buckets[sentiment]["doc_count"]
            row.append(
                {
                    "sentiment": sentiment,
                    "count": count,
                    "proportion_of_mode": (
                        round(count / mode_total, 3) if mode_total else 0.0
                    ),
                    "proportion_of_total": (
                        round(count / total_posts, 3) if total_posts else 0.0
                    ),
                }
            )

        matrix.append(
            {
                "mode": mode,
                "mode_total": mode_total,
                "cells": row,
            }
        )

    return {
        "index": SOCIAL_POSTS_INDEX,
        "total_posts": total_posts,
        "total_posts_is_exact": total_posts_is_exact,
        "modes": TransportModes.names(),
        "sentiments": SentimentLevels.names(),
        "matrix": matrix,
    }
