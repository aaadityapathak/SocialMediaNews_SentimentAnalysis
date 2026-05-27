import os
import time
import logging
import requests
from datetime import datetime

from gdelt_retrieve.harvesters import EventsHarvester, GkgHarvester
from gdelt_retrieve.settings import GdeltStreamSettings
from gdelt_retrieve.schemas import upload_to_elasticsearch_local, USEFUL_COLUMNS

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
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
    target_datetime: datetime, settings: GdeltStreamSettings
):
    os.makedirs(settings.raw_dir, exist_ok=True)
    event_harvester = EventsHarvester(raw_dir=settings.raw_dir)
    gkg_harvester = GkgHarvester(raw_dir=settings.raw_dir)

    logger.info(f"--- Harvesting Events for {target_datetime} ---")
    victoria_events_dict = {}

    for record in event_harvester.run(
        start_date=target_datetime,
        end_date=target_datetime,
        interval="15m",
        delete_raw=True,
        adm1_code=None,
        actor_cameo=None,
    ):
        victoria_events_dict[record.GlobalEventID] = record

    logger.info(f"Found {len(victoria_events_dict)} events for target region.")

    if not victoria_events_dict:
        logger.info("Skipping GKG extraction (no regional events found).")
        return

    logger.info("--- Harvesting GKG & Mapping (Dropping Duplicates) ---")
    combined_dictionaries = []
    victoria_urls_dict = {
        ev.SourceURL: ev for ev in victoria_events_dict.values() if ev.SourceURL
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
                if eid in victoria_events_dict:
                    event_match = victoria_events_dict[eid]
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
        upload_to_elasticsearch_local(
            list(unique_dicts.values()), index_name="gdelt-index"
        )
    else:
        logger.info("No intersecting GKG records found.")


if __name__ == "__main__":
    settings = GdeltStreamSettings()
    last_processed_time = None

    logger.info("=========================================")
    logger.info("  GDELT LIVE STREAMING DAEMON STARTED")
    logger.info(f"  Polling every {settings.poll_interval_seconds} seconds")
    logger.info("=========================================")

    while True:
        latest_time = get_latest_gdelt_timestamp(settings.update_url)

        if latest_time:
            if last_processed_time is None:
                logger.info(
                    f"Daemon Initialized. Current GDELT batch is: {latest_time}"
                )
                last_processed_time = latest_time
                process_and_stream_batch(latest_time, settings)

            elif latest_time > last_processed_time:
                logger.info(f"*** NEW GDELT DATA DETECTED: {latest_time} ***")
                last_processed_time = latest_time
                process_and_stream_batch(latest_time, settings)
            else:
                logger.debug("No new data available yet.")

        time.sleep(settings.poll_interval_seconds)
