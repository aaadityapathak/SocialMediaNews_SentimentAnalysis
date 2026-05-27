from candidates_api import build_query


def test_build_query_no_party():
    """
    Test building the query with no party abbreviation
    :return:
    """
    _ = build_query()


def test_build_query_with_party():
    """
    Test building the query with party abbreviation
    :return:
    """
    _ = build_query(party="ALP")
