from unittest.mock import MagicMock, patch

import pytest
from flask import Flask

import sentiment_matrix_api


@pytest.fixture
def app():
    return Flask(__name__)


@pytest.fixture
def repo():
    sentiment_matrix_api._client.cache_clear()
    with (
        patch.object(sentiment_matrix_api, "Elasticsearch"),
        patch.object(sentiment_matrix_api, "read_from_secret") as rs,
        patch.object(
            sentiment_matrix_api, "get_transport_sentiment_matrix"
        ) as r,
    ):
        rs.return_value = MagicMock(host="https://es", api_key="k")
        r.return_value = {"matrix": [], "totals": {"positive": 0}}
        yield r
    sentiment_matrix_api._client.cache_clear()


def test_year_expands_to_full_year_window(app, repo):
    with app.test_request_context("/?year=2024"):
        body = sentiment_matrix_api.get_transport_sentiment().get_json()

    assert body["filters"] == {
        "platform": None,
        "from": "2024-01-01",
        "to": "2024-12-31",
        "year": 2024,
    }
    assert repo.call_args.kwargs["date_from"] == "2024-01-01"
    assert repo.call_args.kwargs["date_to"] == "2024-12-31"


def test_explicit_dates_take_precedence_over_year(app, repo):
    with app.test_request_context(
        "/?year=2024&from=2024-03-01&to=2024-04-15"
    ):
        body = sentiment_matrix_api.get_transport_sentiment().get_json()

    assert body["filters"]["from"] == "2024-03-01"
    assert body["filters"]["to"] == "2024-04-15"
    assert body["filters"]["year"] == 2024
    assert repo.call_args.kwargs["date_from"] == "2024-03-01"


def test_only_from_keeps_year_untouched(app, repo):
    with app.test_request_context("/?year=2024&from=2024-06-01"):
        body = sentiment_matrix_api.get_transport_sentiment().get_json()

    assert body["filters"]["from"] == "2024-06-01"
    assert body["filters"]["to"] is None
    assert repo.call_args.kwargs["date_to"] is None


def test_platform_filter_pass_through(app, repo):
    with app.test_request_context("/?platform=mastodon&year=2025"):
        body = sentiment_matrix_api.get_transport_sentiment().get_json()

    assert body["filters"]["platform"] == "mastodon"
    assert repo.call_args.kwargs["platform"] == "mastodon"
    assert repo.call_args.kwargs["date_from"] == "2025-01-01"
