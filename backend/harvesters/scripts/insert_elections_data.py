"""
Script for Uploading House Election data to Elastic Search.
This script uploads the AEC Two Candidate Preference Results
for each candidate in the 2025 Australian House elections to ElasticSearch.

To run, you must download the House TCP by Candidate by Polling Place and the
General polling Places from the AEC website here: https://results.aec.gov.au/31496/Website/HouseDownloadsMenu-31496-Csv.htm
Put the files in the same directory without changing their names.

Then you can run the script with
```shell
uv run --env-file .env insert_elections_data.py --data_dir path/to/csvs/directory
```
"""

import pandas as pd
from pathlib import Path
from typing import Iterator
from elastic import ESSettings
from elasticsearch import Elasticsearch

# Must contain data
_DEFAULT_DATA_PATH = Path(__file__).parents[1] / "data"


def load_polling_places_data(data_dir: Path) -> dict:
    """
    Load the polling places dataset. Returns as a mapping of polling place ID
    to polling place information. Includes the polling place location
    coordinates.
    :param data_dir:
    :return:
    """
    fp = data_dir / "GeneralPollingPlacesDownload-31496.csv"
    locations = pd.read_csv(fp, skiprows=1)
    locations.rename(
        {
            "State": "state_code",
            "DivisionID": "division_id",
            "DivisionNm": "division_name",
            "PollingPlaceID": "polling_place_id",
            "PremisesPostCode": "polling_place_post_code",
            "Latitude": "latitude",
            "Longitude": "longitude",
        },
        axis="columns",
        inplace=True,
    )
    processed = {}
    for _, loc in locations.iterrows():
        processed[int(loc["polling_place_id"])] = {
            "id": int(loc["polling_place_id"]),
            "division_id": int(loc["division_id"]),
            "division_name": loc["division_name"],
            "state_code": loc["state_code"],
            "post_code": str(int(loc["polling_place_post_code"]))
            if pd.notnull(loc["polling_place_post_code"])
            else None,
            "location": {
                "lat": float(loc["latitude"]),
                "lon": float(loc["longitude"]),
            }
            if pd.notnull(loc["latitude"])
            else None,
        }
    return processed


def load_preferences_dataset(data_dir: Path) -> pd.DataFrame:
    """
    Load the Two Candidate Preference dataset
    :param data_dir:
    :return:
    """
    fp = data_dir / "HouseTcpByCandidateByPollingPlaceDownload-31496.csv"
    df = pd.read_csv(fp, skiprows=1)
    return df


def prepare_election_data(data_dir: Path) -> Iterator[dict]:
    """
    Yield an iterator over the parsed elections data
    :param data_dir:
    :return:
    """
    preference = load_preferences_dataset(data_dir)
    places = load_polling_places_data(data_dir)

    for _, row in preference.iterrows():
        data = {
            "record_id": "%d-%d" % (row["CandidateID"], row["PollingPlaceID"]),
            "candidate_name": "%s %s" % (row["GivenNm"], row["Surname"]),
            "candidate_id": row["CandidateID"],
            "candidate_given_name": row["GivenNm"],
            "candidate_surname": row["Surname"],
            "party_abbreviation": row["PartyAb"],
            "ballot_position": row["BallotPosition"],
            "ordinary_votes": row["OrdinaryVotes"],
            "party_name": row["PartyNm"],
            "polling_place": places[row["PollingPlaceID"]],
            "division": row["DivisionNm"],
            "swing": row["Swing"],
            "elected": row["Elected"] == "Y",
            "previously_elected": row["HistoricElected"] == "Y",
        }
        if row["Elected"] == "Y" and row["HistoricElected"] == "Y":
            data["candidate_result"] = "KeptSeat"
        elif row["Elected"] == "Y" and row["HistoricElected"] != "Y":
            data["candidate_result"] = "TookSeat"
        elif row["Elected"] != "Y" and row["HistoricElected"] == "Y":
            data["candidate_result"] = "LostSeat"
        elif row["Elected"] != "Y" and row["HistoricElected"] != "Y":
            data["candidate_result"] = "Lost"

        yield data


def load_elections_data(data_dir: str | Path = _DEFAULT_DATA_PATH):
    """
    Load the elections data into the ES index.
    :param data_dir:
    :return:
    """
    settings = ESSettings()
    es = Elasticsearch(
        settings.host, api_key=settings.api_key, verify_certs=False
    )
    with es:
        for element in prepare_election_data(Path(data_dir)):
            record_id = element["record_id"]
            es.index(index="aec-house-tcp", document=element, id=record_id)


if __name__ == "__main__":
    import fire

    fire.Fire(load_elections_data)
