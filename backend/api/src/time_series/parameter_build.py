from typing import Literal
from datetime import datetime, UTC


def sentiment_series_query(
    query_string: str,
    interval: Literal["week", "day", "month"] = "week",
    from_date: datetime | None = None,
    exclude_neutral: bool = False,
) -> dict:
    """
    Get the query parameters to get the time series of sentiment by the given intervals
    :param query_string:
    :param interval:
    :param from_date:
    :param exclude_neutral:
    :return:
    """
    from_date = from_date or datetime(2025, 1, 1).astimezone(UTC)
    bool_query = {
        "must": {
            "query_string": {
                "query": query_string,
                "default_field": "text",
            },
        },
        "filter": {
            "range": {
                "created_at": {
                    "gte": from_date.isoformat(),
                    "lte": datetime.now(UTC).isoformat(),
                }
            }
        },
    }

    if exclude_neutral:
        bool_query["must_not"] = {"term": {"sentiment.sentiment": "neutral"}}
    return {
        "index": "social-posts-index",
        "size": 0,
        "query": {"bool": bool_query},
        "aggs": {
            f"by_{interval}": {
                "date_histogram": {
                    "field": "created_at",
                    "calendar_interval": interval,
                    "format": "yyyy-MM-dd",
                    "min_doc_count": 0,
                },
                "aggs": {
                    "avg_positive": {"avg": {"field": "sentiment.positive"}},
                    "avg_negative": {"avg": {"field": "sentiment.negative"}},
                    "avg_neutral": {"avg": {"field": "sentiment.neutral"}},
                    "total_posts": {"cardinality": {"field": "common_id"}},
                },
            },
        },
    }


def emotions_series_query(
    query_string: str,
    interval: Literal["week", "day", "month"] = "week",
    from_date: datetime | None = None,
    exclude_neutral: bool = False,
):
    """
    Generate query to get the emotions time series
    :param query_string:
    :param interval:
    :param from_date:
    :param exclude_neutral:
    :return:
    """
    from_date = from_date or datetime(2025, 1, 1).astimezone(UTC)
    bool_query = {
        "must": {
            "query_string": {
                "query": query_string,
                "default_field": "text",
            },
        },
        "filter": {
            "range": {
                "created_at": {
                    "gte": from_date.isoformat(),
                    "lte": datetime.now(UTC).isoformat(),
                }
            }
        },
    }
    if exclude_neutral:
        bool_query["must_not"] = {"term": {"sentiment.sentiment": "neutral"}}
    return {
        "index": "social-posts-index",
        "size": 0,
        "query": {"bool": bool_query},
        "aggs": {
            f"by_{interval}": {
                "date_histogram": {
                    "field": "created_at",
                    "calendar_interval": interval,
                    "format": "yyyy-MM-dd",
                    "min_doc_count": 0,
                },
                "aggs": {
                    "emotions": {
                        "nested": {"path": "emotion"},
                        "aggs": {
                            "by_label": {
                                "terms": {"field": "emotion.label", "size": 10},
                                "aggs": {
                                    "avg_score": {
                                        "avg": {"field": "emotion.score"}
                                    }
                                },
                            }
                        },
                    },
                    "total_posts": {"cardinality": {"field": "common_id"}},
                },
            },
        },
    }


def counts_query(
    query_string: str | None,
    interval: Literal["week", "day", "month"] = "week",
    from_date: datetime | None = None,
) -> dict:
    """
    Get the query parameters to get simple time series of matches of a query string.
    :param query_string:
    :param interval:
    :param from_date:
    :return:
    """
    from_date = from_date or datetime(2025, 1, 1).astimezone(UTC)
    bool_query = {
        "filter": {
            "range": {
                "created_at": {
                    "gte": from_date.isoformat(),
                    "lte": datetime.now(UTC).isoformat(),
                }
            }
        },
    }

    if query_string:
        bool_query["must"] = {
            "query_string": {
                "query": query_string,
                "default_field": "text",
            },
        }
    return {
        "index": "social-posts-index",
        "size": 0,
        "query": {"bool": bool_query},
        "aggs": {
            f"by_{interval}": {
                "date_histogram": {
                    "field": "created_at",
                    "calendar_interval": interval,
                    "format": "yyyy-MM-dd",
                    "min_doc_count": 0,
                },
                "aggs": {
                    "total_posts": {"cardinality": {"field": "common_id"}},
                },
            },
        },
    }
