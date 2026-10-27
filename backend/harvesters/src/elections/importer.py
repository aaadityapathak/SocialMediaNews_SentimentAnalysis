"""Chunked AEC CSV parsing and bounded Elasticsearch bulk writes."""

from pathlib import Path

import pandas as pd
from elastic import ESSettings
from elasticsearch import Elasticsearch
from elasticsearch.helpers import streaming_bulk

DEFAULT_DATA_PATH = Path(__file__).resolve().parents[2] / "data"
INDEX = "aec-house-tcp"


def _records(frame):
    # Convert NaN to JSON null and NumPy scalars to ordinary Python values.
    return frame.astype(object).where(frame.notna(), None).to_dict("records")


def load_polling_places_data(data_dir: Path) -> dict:
    locations = pd.read_csv(
        data_dir / "GeneralPollingPlacesDownload-31496.csv", skiprows=1
    )
    processed = {}
    for loc in _records(locations):
        place_id = int(loc["PollingPlaceID"])
        processed[place_id] = {
            "id": place_id,
            "division_id": int(loc["DivisionID"]),
            "division_name": loc["DivisionNm"],
            "state_code": loc["State"],
            "post_code": str(int(loc["PremisesPostCode"]))
            if loc["PremisesPostCode"] is not None
            else None,
            "location": {
                "lat": float(loc["Latitude"]),
                "lon": float(loc["Longitude"]),
            }
            if loc["Latitude"] is not None and loc["Longitude"] is not None
            else None,
        }
    return processed


def load_preferences_dataset(data_dir: Path):
    """Compatibility helper for callers needing a complete dataframe."""
    return pd.read_csv(
        data_dir / "HouseTcpByCandidateByPollingPlaceDownload-31496.csv",
        skiprows=1,
    )


def prepare_election_data(data_dir: Path, chunk_size: int = 5000):
    if chunk_size < 1:
        raise ValueError("chunk_size must be positive")
    places = load_polling_places_data(data_dir)
    path = data_dir / "HouseTcpByCandidateByPollingPlaceDownload-31496.csv"
    with pd.read_csv(path, skiprows=1, chunksize=chunk_size) as chunks:
        for chunk in chunks:
            for row in _records(chunk):
                candidate_id, place_id = (
                    int(row["CandidateID"]),
                    int(row["PollingPlaceID"]),
                )
                elected, previous = (
                    row["Elected"] == "Y",
                    row["HistoricElected"] == "Y",
                )
                if place_id not in places:
                    raise ValueError(
                        f"Unknown polling place {place_id} for candidate {candidate_id}"
                    )
                yield {
                    "record_id": f"{candidate_id}-{place_id}",
                    "candidate_name": f"{row['GivenNm']} {row['Surname']}",
                    "candidate_id": candidate_id,
                    "candidate_given_name": row["GivenNm"],
                    "candidate_surname": row["Surname"],
                    "party_abbreviation": row["PartyAb"],
                    "ballot_position": row["BallotPosition"],
                    "ordinary_votes": row["OrdinaryVotes"],
                    "party_name": row["PartyNm"],
                    "polling_place": places[place_id],
                    "division": row["DivisionNm"],
                    "swing": row["Swing"],
                    "elected": elected,
                    "previously_elected": previous,
                    "candidate_result": {
                        (True, True): "KeptSeat",
                        (True, False): "TookSeat",
                        (False, True): "LostSeat",
                        (False, False): "Lost",
                    }[elected, previous],
                }


def load_elections_data(
    data_dir: str | Path = DEFAULT_DATA_PATH, batch_size: int = 500
):
    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    settings = ESSettings()
    actions = (
        {"_index": INDEX, "_id": document["record_id"], "_source": document}
        for document in prepare_election_data(Path(data_dir))
    )
    count = 0
    with Elasticsearch(
        settings.host, api_key=settings.api_key, verify_certs=False
    ) as es:
        for ok, result in streaming_bulk(
            es,
            actions,
            chunk_size=batch_size,
            max_retries=3,
            raise_on_error=True,
        ):
            if not ok:
                raise RuntimeError(f"Election bulk write failed: {result}")
            count += 1
    return {"indexed": count}
