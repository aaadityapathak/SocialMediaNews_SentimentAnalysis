from elasticsearch import Elasticsearch
from api_schemas import TrendsRequest

from .parameter_build import (
    emotions_series_query,
    sentiment_series_query,
    counts_query,
)


def get_sentiment_timeseries(req: TrendsRequest, client: Elasticsearch):
    """
    Compute the timeseries of sentiment values for the given query.
    :param req:
    :param client:
    :return:
    """
    query_elements = []
    for kw in req.keywords:
        query_elements.append('"%s"' % kw.replace('"', " ").strip())

    query_string = " OR ".join(query_elements)
    parameters = sentiment_series_query(
        query_string,
        from_date=req.start_date,
        exclude_neutral=req.exclude_neutral,
        interval=req.aggregate_by,
    )

    result = client.search(**parameters)
    data = []
    for element in result["aggregations"][f"by_{req.aggregate_by}"]["buckets"]:
        data.append(
            {
                "date": element["key_as_string"],
                "avg_positive": element["avg_positive"]["value"],
                "avg_negative": element["avg_negative"]["value"],
                "avg_neutral": element["avg_neutral"]["value"],
                "total_posts": element["total_posts"]["value"],
            }
        )

    return {"data": data}


def get_emotions_timeseries(req: TrendsRequest, client: Elasticsearch):
    """
    Get the time series of emotions scores. Score is the proportion of posts
    the emotion was detected in with score > 0.5.
    :param req:
    :param client:
    :return:
    """
    query_elements = []
    for kw in req.keywords:
        query_elements.append('"%s"' % kw.replace('"', " ").strip())

    query_string = " OR ".join(query_elements)
    parameters = emotions_series_query(
        query_string,
        from_date=req.start_date,
        interval=req.aggregate_by,
        exclude_neutral=req.exclude_neutral,
    )

    result = client.search(**parameters)
    data = []
    for element in result["aggregations"][f"by_{req.aggregate_by}"]["buckets"]:
        doc_count = element["total_posts"]["value"]
        emotions = {
            emote["key"]: emote["doc_count"] / doc_count
            for emote in element["emotions"]["by_label"]["buckets"]
        }
        data.append(
            {
                "date": element["key_as_string"],
                "emotions": emotions,
                "total_posts": doc_count,
            }
        )

    return {"data": data}


def get_pct_mentions_timeseries(req: TrendsRequest, client: Elasticsearch):
    """
    Get time series with the ratio of posts that match a certain query.
    :param req:
    :param client:
    :return:
    """
    query_elements = []
    for kw in req.keywords:
        query_elements.append('"%s"' % kw.replace('"', "").strip())

    query_string = " OR ".join(query_elements)
    all_qry = counts_query(None, req.aggregate_by, req.start_date)
    term_qry = counts_query(query_string, req.aggregate_by, req.start_date)
    term_count = client.search(**term_qry)
    all_count = client.search(**all_qry)

    # terms count to dictionary
    terms_dct = {
        element["key_as_string"]: element["total_posts"]["value"]
        for element in term_count["aggregations"][f"by_{req.aggregate_by}"][
            "buckets"
        ]
    }
    data = []
    for element in all_count["aggregations"][f"by_{req.aggregate_by}"][
        "buckets"
    ]:
        date = element["key_as_string"]
        data.append(
            {
                "date": date,
                "pct_mentioned": 100.0 * terms_dct.get(date, 0.0)
                / element["total_posts"]["value"],
                "total_posts": element["total_posts"]["value"],
            }
        )

    return {"data": data}
