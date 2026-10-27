"""Bounded GDELT backfills using the same parsing and joins as live ingestion."""

import argparse
import csv
import logging
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from datetime import datetime, timedelta
from pathlib import Path

from elastic.settings import ESSettings
from elasticsearch import Elasticsearch

from .harvesters import EventsHarvester, GkgHarvester
from .schemas import USEFUL_COLUMNS, upload_to_elasticsearch
from .streamer import iter_joined_records

logger = logging.getLogger(__name__)


def process_single_day(
    target_date,
    overall_start,
    overall_end,
    interval,
    delete_raw,
    raw_dir,
):
    day_start = max(
        target_date.replace(hour=0, minute=0, second=0, microsecond=0),
        overall_start,
    )
    day_end = min(
        target_date.replace(hour=23, minute=59, second=59, microsecond=0),
        overall_end,
    )
    options = {
        "start_date": day_start,
        "end_date": day_end,
        "interval": interval,
        "delete_raw": delete_raw,
        "adm1_code": None,
        "raise_on_download_error": True,
    }
    events = list(EventsHarvester(raw_dir).run(actor_cameo=None, **options))
    rows = []
    if events:
        gkg = GkgHarvester(raw_dir).run(**options)
        try:
            rows = list(iter_joined_records(events, gkg))
        finally:
            gkg.close()
    return {
        "data": rows,
        "msg": f"[{target_date:%Y%m%d}] Harvested {len(rows)} unique documents.",
    }


def iter_backfill_results(
    start,
    end,
    *,
    interval="daily",
    delete_raw=True,
    raw_dir="data/gdelt/raw",
    max_workers=4,
):
    """Keep at most max_workers daily datasets in flight at any time."""
    if start > end:
        raise ValueError("start must not be after end")
    if max_workers < 1:
        raise ValueError("max_workers must be positive")
    if interval not in {"daily", "15m"}:
        raise ValueError("interval must be 'daily' or '15m'")

    def days():
        day = start.replace(hour=0, minute=0, second=0, microsecond=0)
        while day <= end:
            yield day
            day += timedelta(days=1)

    pending_days = iter(days())
    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        pending = {}

        def schedule():
            day = next(pending_days, None)
            if day is None:
                return False
            future = executor.submit(
                process_single_day,
                day,
                start,
                end,
                interval,
                delete_raw,
                raw_dir,
            )
            pending[future] = day
            return True

        for _ in range(max_workers):
            if not schedule():
                break
        try:
            while pending:
                completed, _ = wait(pending, return_when=FIRST_COMPLETED)
                for future in completed:
                    day = pending.pop(future)
                    yield day, future.result()
                    schedule()
        finally:
            for future in pending:
                future.cancel()


def run_backfill(
    start,
    end,
    *,
    interval="daily",
    delete_raw=True,
    raw_dir="data/gdelt/raw",
    backup_dir="data/gdelt/backups",
    index_name="gdelt-events",
    max_workers=4,
):
    """Back up and index each day before scheduling more work."""
    backups = Path(backup_dir)
    backups.mkdir(parents=True, exist_ok=True)
    settings = ESSettings()
    total = 0
    with Elasticsearch(
        settings.host,
        api_key=settings.api_key,
        verify_certs=False,
        request_timeout=60,
    ) as client:
        results = iter_backfill_results(
            start,
            end,
            interval=interval,
            delete_raw=delete_raw,
            raw_dir=raw_dir,
            max_workers=max_workers,
        )
        try:
            for day, result in results:
                logger.info(result["msg"])
                rows = result["data"]
                if not rows:
                    continue
                backup = backups / f"gdelt_{day:%Y%m%d}_{interval}.csv"
                with backup.open("w", newline="", encoding="utf-8") as output:
                    writer = csv.DictWriter(
                        output, fieldnames=USEFUL_COLUMNS, extrasaction="ignore"
                    )
                    writer.writeheader()
                    writer.writerows(rows)
                total += upload_to_elasticsearch(client, rows, index_name)
        finally:
            results.close()
    return total


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", required=True, type=datetime.fromisoformat)
    parser.add_argument("--end", required=True, type=datetime.fromisoformat)
    parser.add_argument("--interval", choices=("daily", "15m"), default="daily")
    parser.add_argument("--raw-dir", default="data/gdelt/raw")
    parser.add_argument("--backup-dir", default="data/gdelt/backups")
    parser.add_argument("--index-name", default="gdelt-events")
    parser.add_argument("--max-workers", type=int, default=4)
    parser.add_argument("--keep-raw", action="store_true")
    options = vars(parser.parse_args())
    options["delete_raw"] = not options.pop("keep_raw")
    logging.basicConfig(level=logging.INFO)
    logger.info("Indexed %s GDELT documents", run_backfill(**options))
