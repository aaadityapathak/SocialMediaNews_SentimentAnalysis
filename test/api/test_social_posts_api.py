from unittest.mock import MagicMock, patch

import pytest
from flask import Flask

import social_posts_api


@pytest.fixture
def app():
    return Flask(__name__)


@pytest.fixture
def repo():
    social_posts_api._client.cache_clear()
    with (
        patch.object(social_posts_api, "Elasticsearch"),
        patch.object(social_posts_api, "read_from_secret") as rs,
        patch.object(social_posts_api, "get_transport_group_counts") as r,
    ):
        rs.return_value = MagicMock(host="https://es", api_key="k")
        r.return_value = {"groups": []}
        yield r
    social_posts_api._client.cache_clear()


def test_filters_are_forwarded_to_repository(app, repo):
    repo.return_value = {"groups": [{"mode": "car", "count": 12}]}
    with app.test_request_context(
        "/?platform=bluesky&from=2024-01-01&to=2024-06-30"
    ):
        body = social_posts_api.get_transport_groups().get_json()

    assert body["filters"] == {
        "platform": "bluesky",
        "from": "2024-01-01",
        "to": "2024-06-30",
    }
    assert body["groups"] == [{"mode": "car", "count": 12}]
    assert repo.call_args.kwargs == {
        "platform": "bluesky",
        "date_from": "2024-01-01",
        "date_to": "2024-06-30",
    }


def test_no_filters_passes_none(app, repo):
    with app.test_request_context("/"):
        body = social_posts_api.get_transport_groups().get_json()

    assert body["filters"] == {"platform": None, "from": None, "to": None}
    assert repo.call_args.kwargs == {
        "platform": None,
        "date_from": None,
        "date_to": None,
    }


def test_partial_filter_only_platform(app, repo):
    with app.test_request_context("/?platform=mastodon"):
        body = social_posts_api.get_transport_groups().get_json()

    assert body["filters"]["platform"] == "mastodon"
    assert body["filters"]["from"] is None
    assert body["filters"]["to"] is None
