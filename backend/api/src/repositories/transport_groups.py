from typing import Any

from elasticsearch import Elasticsearch

from constants.indexes import SOCIAL_POSTS_INDEX
from constants.transport_groups import TransportGroups


def _base_filters(
    platform: str | None,
    date_from: str | None,
    date_to: str | None,
) -> list[dict]:
    filters: list[dict] = [{"exists": {"field": "text"}}]
    if platform:
        filters.append({"term": {"platform": platform}})
    if date_from or date_to:
        rng: dict[str, str] = {}
        if date_from:
            rng["gte"] = date_from
        if date_to:
            rng["lte"] = date_to
        filters.append({"range": {"created_at": rng}})
    return filters


def _group_filters() -> dict[str, dict]:
    return {
        name: {
            "simple_query_string": {
                "query": query,
                "fields": ["text"],
                "default_operator": "or",
            }
        }
        for name, query in TransportGroups.as_queries().items()
    }


def get_transport_group_counts(
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
            "bool": {
                "filter": _base_filters(platform, date_from, date_to),
            }
        },
        "aggs": {
            "transport_groups": {
                "filters": {"filters": _group_filters()},
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
    buckets = result["aggregations"]["transport_groups"]["buckets"]
    total_hits = result["hits"]["total"]
    total_posts = total_hits["value"]
    total_posts_is_exact = total_hits.get("relation") == "eq"

    groups = [
        {
            "group": name,
            "count": buckets[name]["doc_count"],
            "proportion": (
                round(buckets[name]["doc_count"] / total_posts, 3)
                if total_posts
                else 0.0
            ),
        }
        for name in TransportGroups.names()
    ]

    return {
        "index": SOCIAL_POSTS_INDEX,
        "total_posts": total_posts,
        "total_posts_is_exact": total_posts_is_exact,
        "groups": groups,
    }
