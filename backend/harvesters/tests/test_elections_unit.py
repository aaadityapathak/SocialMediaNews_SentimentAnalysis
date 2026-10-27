import csv
import json
from unittest.mock import MagicMock

import pytest
from elections import importer


def write_csv(path, headers, rows):
    with path.open("w", newline="", encoding="utf-8") as stream:
        stream.write("AEC dataset metadata\n")
        writer = csv.writer(stream)
        writer.writerow(headers)
        writer.writerows(rows)


@pytest.fixture
def election_data(tmp_path):
    write_csv(
        tmp_path / "GeneralPollingPlacesDownload-31496.csv",
        [
            "State",
            "DivisionID",
            "DivisionNm",
            "PollingPlaceID",
            "PremisesPostCode",
            "Latitude",
            "Longitude",
        ],
        [
            ["VIC", 1, "Test", 2, 3000, -37, 144],
            ["VIC", 1, "Test", 3, "", -37, ""],
        ],
    )
    write_csv(
        tmp_path / "HouseTcpByCandidateByPollingPlaceDownload-31496.csv",
        [
            "CandidateID",
            "PollingPlaceID",
            "GivenNm",
            "Surname",
            "PartyAb",
            "BallotPosition",
            "OrdinaryVotes",
            "PartyNm",
            "DivisionNm",
            "Swing",
            "Elected",
            "HistoricElected",
        ],
        [
            [10, 2, "A", "Person", "P", 1, 20, "Party", "Test", "", "Y", "N"],
            [11, 3, "B", "Person", "P", 2, 10, "Party", "Test", 1.0, "N", "Y"],
        ],
    )
    return tmp_path


def test_chunked_csv_preserves_ids_results_and_json_nulls(election_data):
    rows = list(importer.prepare_election_data(election_data, chunk_size=1))
    assert [r["record_id"] for r in rows] == ["10-2", "11-3"]
    assert [r["candidate_result"] for r in rows] == ["TookSeat", "LostSeat"]
    assert rows[0]["swing"] is None
    assert rows[1]["polling_place"]["location"] is None
    json.dumps(rows, allow_nan=False)


def test_bulk_import_uses_stable_ids_and_closes_client(
    election_data, monkeypatch
):
    es = MagicMock()
    es.__enter__.return_value = es
    monkeypatch.setattr(
        importer,
        "ESSettings",
        lambda: MagicMock(host="https://es", api_key="key"),
    )
    monkeypatch.setattr(importer, "Elasticsearch", lambda *a, **k: es)

    def bulk(client, actions, **kwargs):
        assert client is es
        assert kwargs["chunk_size"] == 1
        for action in actions:
            assert action["_id"] == action["_source"]["record_id"]
            yield True, {}

    monkeypatch.setattr(importer, "streaming_bulk", bulk)
    assert importer.load_elections_data(election_data, batch_size=1) == {
        "indexed": 2
    }
    es.__exit__.assert_called_once()


def test_bulk_import_failure_propagates_and_closes(election_data, monkeypatch):
    es = MagicMock()
    monkeypatch.setattr(importer, "ESSettings", lambda: MagicMock())
    monkeypatch.setattr(importer, "Elasticsearch", lambda *a, **k: es)
    monkeypatch.setattr(
        importer,
        "streaming_bulk",
        lambda *a, **k: iter([(False, {"error": "bad"})]),
    )
    with pytest.raises(RuntimeError, match="bulk write failed"):
        importer.load_elections_data(election_data)
    es.__exit__.assert_called_once()


@pytest.mark.parametrize("size", [0, -1])
def test_invalid_batch_size_rejected(size):
    with pytest.raises(ValueError, match="positive"):
        importer.load_elections_data(batch_size=size)
