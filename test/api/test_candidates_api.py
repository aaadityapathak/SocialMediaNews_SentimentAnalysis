from unittest.mock import MagicMock, patch

import pytest
from flask import Flask

import candidates_api


CANDIDATE_COLUMNS = [
    {"name": "party_abbreviation"},
    {"name": "candidate_given_name"},
    {"name": "candidate_surname"},
    {"name": "total_votes"},
]


def _candidates_response(rows):
    return {"columns": CANDIDATE_COLUMNS, "values": rows}


@pytest.fixture
def app():
    return Flask(__name__)


@pytest.fixture
def es():
    with (
        patch.object(candidates_api, "Elasticsearch") as cls,
        patch.object(candidates_api, "read_from_secret") as rs,
    ):
        rs.return_value = MagicMock(host="https://es", api_key="k")
        client = MagicMock()
        cls.return_value = client
        yield client


@pytest.fixture
def build_query_spy():
    with patch.object(
        candidates_api, "build_query", wraps=candidates_api.build_query
    ) as bq:
        yield bq


def test_candidates_filter_by_party(app, es, build_query_spy):
    es.esql.query.return_value = _candidates_response(
        [["ALP", "Anthony", "Albanese", 12345]]
    )
    with app.test_request_context("/?party_abbrev=ALP&limit=3"):
        result = candidates_api.get_top_voted_candidates()

    build_query_spy.assert_called_once_with(3, "ALP")
    assert result["candidates"][0]["party_abbreviation"] == "ALP"
    assert result["candidates"][0]["total_votes"] == 12345


def test_candidates_default_limit_and_no_party(app, es, build_query_spy):
    es.esql.query.return_value = _candidates_response([])
    with app.test_request_context("/"):
        result = candidates_api.get_top_voted_candidates()

    build_query_spy.assert_called_once_with(60, None)
    assert result == {"candidates": []}


def test_candidates_invalid_limit_falls_back_to_default(app, es, build_query_spy):
    es.esql.query.return_value = _candidates_response([])
    with app.test_request_context("/?limit=NAN"):
        candidates_api.get_top_voted_candidates()

    assert build_query_spy.call_args.args[0] == 60


def test_top_parties_maps_rows(app, es):
    es.esql.query.return_value = {
        "columns": [
            {"name": "party_name"},
            {"name": "party_abbreviation"},
            {"name": "total_candidates"},
            {"name": "total_elected"},
        ],
        "values": [
            ["Labor", "ALP", 151, 77],
            ["Liberal", "LP", 150, 56],
            ["Greens", "GRN", 100, 4],
        ],
    }
    with app.test_request_context("/"):
        result = candidates_api.get_top_parties()

    abbrevs = [p["party_abbreviation"] for p in result["parties"]]
    assert abbrevs == ["ALP", "LP", "GRN"]
    assert result["parties"][0]["total_elected"] == 77
