import time
import logging
import requests
import tempfile
from datetime import datetime

from .harvesters import EventsHarvester, GkgHarvester
from .settings import GdeltStreamSettings
from .schemas import upload_to_elasticsearch, USEFUL_COLUMNS

logger = logging.getLogger("gdelt_streamer")


def get_latest_gdelt_timestamp(url: str) -> datetime | None:
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        first_line = response.text.strip().split("\n")[0]
        file_url = first_line.split(" ")[2]
        timestamp_str = file_url.split("/")[-1].split(".")[0]
        return datetime.strptime(timestamp_str, "%Y%m%d%H%M%S")
    except Exception as e:
        logger.error(f"Failed to fetch latest GDELT update: {e}")
        return None


def process_and_stream_batch(
    target_datetime: datetime, settings: GdeltStreamSettings, es_client
) -> int:
    time.sleep(5)

    with tempfile.TemporaryDirectory() as temp_raw_dir:
        event_harvester = EventsHarvester(raw_dir=temp_raw_dir)
        gkg_harvester = GkgHarvester(raw_dir=temp_raw_dir)

        logger.info(f"--- Harvesting Events for {target_datetime} ---")
        aus_events_dict = {}

        for record in event_harvester.run(
            start_date=target_datetime,
            end_date=target_datetime,
            interval="15m",
            delete_raw=True,
            adm1_code=None,
            actor_cameo=None,
        ):
            aus_events_dict[record.GlobalEventID] = record

        logger.info(f"Found {len(aus_events_dict)} events for target region.")

        if not aus_events_dict:
            logger.info("Skipping GKG extraction (no regional events found).")
            return 0

        logger.info("--- Harvesting GKG & Mapping (Dropping Duplicates) ---")
        combined_dictionaries = []
        victoria_urls_dict = {
            ev.SourceURL: ev for ev in aus_events_dict.values() if ev.SourceURL
        }

        for gkg_record in gkg_harvester.run(
            start_date=target_datetime,
            end_date=target_datetime,
            interval="15m",
            delete_raw=True,
            adm1_code=None,
        ):
            event_match = None

            if gkg_record.CAMEOEVENTIDS:
                linked_ids = [
                    eid.strip()
                    for eid in gkg_record.CAMEOEVENTIDS.split(",")
                    if eid.strip()
                ]
                for eid in linked_ids:
                    if eid in aus_events_dict:
                        event_match = aus_events_dict[eid]
                        break

            if (
                not event_match
                and gkg_record.SOURCEURLS
                and gkg_record.SOURCEURLS in victoria_urls_dict
            ):
                event_match = victoria_urls_dict[gkg_record.SOURCEURLS]

            if event_match:
                combined_dict = dict(
                    zip(EventsHarvester.COLUMN_HEADERS, event_match.to_row())
                )

                combined_dict["GKG_COUNTS"] = gkg_record.COUNTS
                combined_dict["GKG_THEMES"] = gkg_record.THEMES
                combined_dict["GKG_PERSONS"] = gkg_record.PERSONS
                combined_dict["GKG_ORGANIZATIONS"] = gkg_record.ORGANIZATIONS
                combined_dict["GKG_TONE"] = gkg_record.TONE

                # --- EXACT TIMESTAMP FIX ---
                combined_dict["DateAdded"] = target_datetime.strftime(
                    "%Y%m%d%H%M%S"
                )

                # --- INSTANT COLUMN FILTERING ---
                filtered_dict = {
                    k: combined_dict[k]
                    for k in USEFUL_COLUMNS
                    if k in combined_dict
                }
                combined_dictionaries.append(filtered_dict)

        if combined_dictionaries:
            unique_dicts = {
                f"{d['GlobalEventID']}_{d['SourceURL']}": d
                for d in combined_dictionaries
            }
            success_count = upload_to_elasticsearch(
                es_client,
                list(unique_dicts.values()),
                index_name="gdelt-index",
            )
            return success_count

        return 0
