import os
import multiprocessing
import pandas as pd
import numpy as np
import urllib3
from datetime import datetime, timedelta
from concurrent.futures import ProcessPoolExecutor, as_completed
from elasticsearch import Elasticsearch, helpers
from tqdm import tqdm
from gdelt_retrieve import EventsHarvester, GkgHarvester

# SINGLE SOURCE OF TRUTH IMPORT
from gdelt_retrieve.schemas import generate_actions_from_memory, USEFUL_COLUMNS


def process_single_day(
    target_date, overall_start, overall_end, interval, delete_raw, raw_dir
):
    day_start = (
        overall_start
        if target_date.date() == overall_start.date()
        else target_date.replace(hour=0, minute=0, second=0, microsecond=0)
    )
    day_end = (
        overall_end
        if target_date.date() == overall_end.date()
        else target_date.replace(hour=23, minute=59, second=59, microsecond=0)
    )

    date_label = target_date.strftime("%Y%m%d")
    event_harvester = EventsHarvester(raw_dir=raw_dir)
    gkg_harvester = GkgHarvester(raw_dir=raw_dir)
    victoria_events_dict = {}

    for record in event_harvester.run(
        start_date=day_start,
        end_date=day_end,
        interval=interval,
        delete_raw=delete_raw,
        adm1_code=None,
        actor_cameo=None,
    ):
        victoria_events_dict[record.GlobalEventID] = record

    if not victoria_events_dict:
        return {
            "data": [],
            "msg": f"[{date_label}] No events found in Victoria. Skipping GKG.",
        }

    combined_dictionaries = []
    victoria_urls_dict = {
        ev.SourceURL: ev for ev in victoria_events_dict.values() if ev.SourceURL
    }

    for gkg_record in gkg_harvester.run(
        start_date=day_start,
        end_date=day_end,
        interval=interval,
        delete_raw=delete_raw,
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

            # --- STRING COERCION TIMESTAMP FIX ---
            raw_date = str(combined_dict.get("DateAdded", "")).split(".")[0]
            if len(raw_date) >= 8:
                combined_dict["DateAdded"] = raw_date.ljust(14, "0")

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
        extracted_data = list(unique_dicts.values())
        return {
            "data": extracted_data,
            "msg": f"[{date_label}] SUCCESS: Harvested {len(extracted_data)} unique documents.",
        }
    else:
        return {
            "data": [],
            "msg": f"[{date_label}] Exported events, but no GKG matches found.",
        }


if __name__ == "__main__":
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    ES_HOST = os.getenv("ELASTIC_HOST", "https://localhost:9200")
    ES_API_KEY = os.getenv("ELASTIC_API_KEY")
    INDEX_NAME = os.getenv("INDEX_NAME", "gdelt-events")

    START_DATE = datetime(2024, 1, 1, 0, 0, 0)
    END_DATE = datetime(2025, 12, 31, 23, 59, 59)

    INTERVAL = "daily"
    DELETE_RAW_AFTER = True

    RAW_DIR = "./data/gdelt/gdelt_raw_data"
    BACKUP_DIR = "./data/gdelt/gdelt_backfill_backups"

    os.makedirs(RAW_DIR, exist_ok=True)
    os.makedirs(BACKUP_DIR, exist_ok=True)

    MAX_WORKERS = max(1, multiprocessing.cpu_count() - 1)

    print("Starting GDELT Harvest & Batch Push Pipeline...")
    print(f"Date Range: {START_DATE} to {END_DATE}")
    print(f"Parallel Nodes Allocated: {MAX_WORKERS}")
    print("-" * 50)

    days_to_process = []
    current = START_DATE.replace(hour=0, minute=0, second=0, microsecond=0)
    end = END_DATE.replace(hour=0, minute=0, second=0, microsecond=0)

    while current <= end:
        days_to_process.append(current)
        current += timedelta(days=1)

    master_data_list = []

    with ProcessPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {
            executor.submit(
                process_single_day,
                day,
                START_DATE,
                END_DATE,
                INTERVAL,
                DELETE_RAW_AFTER,
                RAW_DIR,
            ): day
            for day in days_to_process
        }

        for future in as_completed(futures):
            target_day = futures[future]
            try:
                result = future.result()
                print(result["msg"])
                master_data_list.extend(result["data"])
            except Exception as e:
                print(f"[{target_day.strftime('%Y%m%d')}] ERROR: {str(e)}")

    print("-" * 50)
    print(
        f"Harvesting Phase Complete. Total documents gathered: {len(master_data_list)}"
    )

    if master_data_list:
        print("Executing Global Deduplication...")
        global_unique = {
            f"{d['GlobalEventID']}_{d['SourceURL']}": d
            for d in master_data_list
        }
        final_batch = list(global_unique.values())

        backup_filename = f"gdelt_backup_{START_DATE.strftime('%Y%m%d')}_{END_DATE.strftime('%Y%m%d')}.csv"
        backup_path = os.path.join(BACKUP_DIR, backup_filename)
        df = pd.DataFrame(final_batch)

        print(f"Saving fault-tolerance CSV backup to: {backup_path}")
        try:
            df.to_csv(backup_path, index=False)
            print(f"SUCCESS: Local backup saved ({len(final_batch)} rows).")
        except Exception as e:
            print(f"WARNING: Failed to save local backup CSV: {e}")

        print("Cleaning missing values for JSON compatibility...")
        df = df.replace("nan", np.nan)
        df = df.astype(object).replace({np.nan: None})

        cleaned_records = df.to_dict(orient="records")

        print(
            f"Initiating MULTI-THREADED Bulk Upload to Elasticsearch ({len(cleaned_records)} unique documents)..."
        )

        es_client = Elasticsearch(
            ES_HOST,
            api_key=ES_API_KEY,
            verify_certs=False,
            request_timeout=60,
            max_retries=3,
            retry_on_timeout=True,
        )

        success_count = 0
        for success, info in tqdm(
            helpers.parallel_bulk(
                client=es_client,
                actions=generate_actions_from_memory(
                    cleaned_records, "gdelt-events"
                ),
                thread_count=12,  # Ryzen 7 Optimized
                queue_size=24,
                chunk_size=1500,
                raise_on_error=False,
            ),
            total=len(cleaned_records),
            desc="Uploading to ES",
        ):
            if success:
                success_count += 1
            else:
                print(f"\nFailed to index document: {info}")

        print(
            f"\nSUCCESS: Multi-threaded batch uploaded {success_count} documents to ES."
        )
    else:
        print("No data was harvested to upload.")

    print("Multi-node Backfill Complete!")
