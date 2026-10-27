"""Compatibility CLI for AEC election ingestion.

Download GeneralPollingPlacesDownload-31496.csv and
HouseTcpByCandidateByPollingPlaceDownload-31496.csv into the same data directory.
New callers can use `python -m elections --data_dir path/to/csvs` from src.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from elections.importer import (  # noqa: E402, F401
    load_elections_data,
    load_polling_places_data,
    load_preferences_dataset,
    prepare_election_data,
)

if __name__ == "__main__":
    import fire

    fire.Fire(load_elections_data)
