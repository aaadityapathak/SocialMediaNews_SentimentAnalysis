from datetime import datetime, UTC, timedelta

import pytest

pytestmark = pytest.mark.integration

from api_schemas import TrendsRequest

from time_series import (
    get_emotions_timeseries,
    get_sentiment_timeseries,
    get_pct_mentions_timeseries,
)


def test_sentiment_ts(es_client):
    """
    Test computing a sentiment timeseries
    :return:
    """
    req = TrendsRequest(
        topic_name="Test",
        exclude_neutral=False,
        start_date=datetime.now(UTC) - timedelta(days=120),
        keywords=["Australia", "Music", "world"],  # We just need some results
    )
    resp = get_sentiment_timeseries(req, es_client)
    assert len(resp["data"]) > 0
    for e in resp["data"]:
        assert "date" in e
        assert "avg_positive" in e
        assert "avg_negative" in e
        assert "avg_neutral" in e


def test_emotion_ts(es_client):
    """
    Test computing a sentiment timeseries
    :return:
    """
    req = TrendsRequest(
        topic_name="Test",
        exclude_neutral=False,
        start_date=datetime.now(UTC) - timedelta(days=120),
        keywords=["Australia", "Music", "world"],  # We just need some results
    )
    resp = get_emotions_timeseries(req, es_client)
    assert len(resp["data"]) > 0
    for e in resp["data"]:
        assert "date" in e
        assert "emotions" in e
        assert isinstance(e["emotions"], dict)


def test_sentiment__no_neutral_ts(es_client):
    """
    Test computing a sentiment timeseries (excluding neutral posts)
    :return:
    """
    req = TrendsRequest(
        topic_name="Test",
        exclude_neutral=True,
        start_date=datetime.now(UTC) - timedelta(days=180),
        keywords=[
            "Australia",
            "Cities",
            "world",
            "events",
        ],  # We just need some results
    )
    resp = get_sentiment_timeseries(req, es_client)
    assert len(resp["data"]) > 0
    for e in resp["data"]:
        assert "date" in e
        assert "avg_positive" in e
        assert "avg_negative" in e
        assert "avg_neutral" in e

        # Score should be smaller than 0.5 if we are excluding these posts
        assert e["avg_neutral"] < 0.5


def test_emotion_no_neutral_ts(es_client):
    """
    Test computing a emotion timeseries with no neutral sentiment
    :return:
    """
    req = TrendsRequest(
        topic_name="Test",
        exclude_neutral=True,
        start_date=datetime.now(UTC) - timedelta(days=120),
        keywords=["Australia", "Music", "world"],  # We just need some results
    )
    resp = get_emotions_timeseries(req, es_client)
    assert len(resp["data"]) > 0
    for e in resp["data"]:
        assert "date" in e
        assert "emotions" in e
        assert isinstance(e["emotions"], dict)


def test_pct_mentions_ts(es_client):
    """
    Test the proportion of matches time series
    :return:
    """
    req = TrendsRequest(
        topic_name="Test",
        exclude_neutral=True,
        start_date=datetime.now(UTC) - timedelta(days=120),
        keywords=["Australia", "Music", "food"],  # We just need some results
    )
    resp = get_pct_mentions_timeseries(req, es_client)
    assert len(resp["data"]) > 0
    for e in resp["data"]:
        assert "date" in e
        assert "pct_mentioned" in e
        assert e["pct_mentioned"] <= 100
