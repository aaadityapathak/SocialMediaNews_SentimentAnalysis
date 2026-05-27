import urllib3
import logging
from flask import request
from elasticsearch import Elasticsearch
from elasticsearch.esql import E, ESQL, functions

from settings import ESSettings
from base import read_from_secret, setup_logging

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
setup_logging()

logger = logging.getLogger(__name__)

TOP_PARTIES = """
FROM aec-house-tcp
| STATS was_elected = MAX(CASE(elected, 1, 0)) BY party_name, party_abbreviation, candidate_id
| STATS total_candidates = COUNT_DISTINCT(candidate_id), total_elected = SUM(was_elected) BY party_name, party_abbreviation
| SORT total_elected DESC
"""


def build_query(limit: int = 60, party: str | None = None):
    """
    Build ESQL query to get top candidates.
    :param limit:
    :param party:
    :return:
    """
    top_voted_candidates = ESQL.from_("aec-house-tcp")

    if party:
        top_voted_candidates = top_voted_candidates.where(
            E("party_abbreviation") == party
        )

    top_voted_candidates = (
        top_voted_candidates.stats(
            total_votes=functions.sum(E("ordinary_votes"))
        )
        .by(
            "party_abbreviation",
            "party_name",
            "candidate_id",
            "candidate_given_name",
            "candidate_surname",
            "elected",
            "polling_place.state_code",
            "polling_place.division_name",
        )
        .rename(
            **{
                "polling_place.state_code": "state",
                "polling_place.division_name": "division",
            }
        )
        .sort(E("total_votes").desc())
        .limit(limit)
    )
    return top_voted_candidates


def get_top_voted_candidates():
    """
    Get the top voted candidates from the last elections. Gives candidates with their
    total number of votes.
    Receives the following query parameters:
    - total: Limit candidates to receive. Integer, default=60
    - party_abbrev: Optional party abbreviation to filter results
    :return:
    """
    es_settings = read_from_secret("elastic-api-credentials", ESSettings)
    es = Elasticsearch(
        es_settings.host, api_key=es_settings.api_key, verify_certs=False
    )
    party = request.args.get("party_abbrev")
    limit = request.args.get("limit", type=int, default=60)
    query = build_query(limit, party)

    result = es.esql.query(query=query)
    logger.info("Ran query for top candidates")
    columns = [c["name"] for c in result["columns"]]
    records = [dict(zip(columns, vals)) for vals in result["values"]]
    return {"candidates": records}


def get_top_parties():
    """
    Get the top political parties (by number of elected candidates) from the
    last elections. Gives parties with their abbreviations and total candidates
    elected.
    Receives the following query parameters:
    - total: Limit candidates to receive. Integer, default=60
    - party_abbrev: Optional party abbreviation to filter results
    :return:
    """
    es_settings = read_from_secret("elastic-api-credentials", ESSettings)
    es = Elasticsearch(
        es_settings.host, api_key=es_settings.api_key, verify_certs=False
    )

    result = es.esql.query(query=TOP_PARTIES)
    logger.info("Ran query for top parties")
    columns = [c["name"] for c in result["columns"]]
    records = [dict(zip(columns, vals)) for vals in result["values"]]
    return {"parties": records}
