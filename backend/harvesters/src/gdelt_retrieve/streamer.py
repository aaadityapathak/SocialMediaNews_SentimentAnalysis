"""Join and stream a GDELT update without materializing all enriched documents."""

import logging
import tempfile
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

import requests

from .file_client import create_session
from .harvesters import EventsHarvester, GkgHarvester
from .schemas import USEFUL_COLUMNS, upload_to_elasticsearch
from .settings import GdeltStreamSettings

logger = logging.getLogger(__name__)


def get_latest_gdelt_timestamp(url: str) -> datetime | None:
    try:
        with (
            create_session() as session,
            session.get(url, timeout=(10, 10)) as response,
        ):
            response.raise_for_status()
            for line in response.text.splitlines():
                fields = line.split()
                if len(fields) != 3:
                    continue
                filename = urlsplit(fields[2]).path.rsplit("/", 1)[-1]
                if filename.endswith(".export.CSV.zip"):
                    return datetime.strptime(
                        filename.split(".")[0], "%Y%m%d%H%M%S"
                    )
        raise ValueError("No event archive found in update manifest")
    except (requests.RequestException, ValueError) as exc:
        logger.error("Failed to fetch latest GDELT update: %s", exc)
        return None


def iter_joined_records(events, gkg_records, target_datetime=None):
    """Yield every matching event, including events sharing an article URL."""
    by_id = {event.GlobalEventID: event for event in events}
    by_url = defaultdict(list)
    for event in by_id.values():
        if event.SourceURL:
            by_url[event.SourceURL].append(event)
    seen = set()
    for gkg in gkg_records:
        matches = {
            eid.strip(): by_id[eid.strip()]
            for eid in gkg.CAMEOEVENTIDS.split(",")
            if eid.strip() in by_id
        }
        urls = (
            [gkg.SOURCEURLS]
            if gkg.SOURCEURLS in by_url
            else gkg.SOURCEURLS.split(";")
        )
        for url in urls:
            for event in by_url.get(url.strip(), ()):
                matches[event.GlobalEventID] = event
        for event in matches.values():
            key = (event.GlobalEventID, event.SourceURL)
            if key in seen:
                continue
            seen.add(key)
            row = {
                key: getattr(event, key)
                for key in USEFUL_COLUMNS
                if hasattr(event, key)
            }
            row.update(
                GKG_THEMES=gkg.THEMES,
                GKG_PERSONS=gkg.PERSONS,
                GKG_ORGANIZATIONS=gkg.ORGANIZATIONS,
                GKG_TONE=gkg.TONE,
            )
            if target_datetime is not None:
                row["DateAdded"] = target_datetime.strftime("%Y%m%d%H%M%S")
            yield row


def process_and_stream_batch(
    target_datetime: datetime, settings: GdeltStreamSettings, es_client
) -> int:
    Path(settings.raw_dir).mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=settings.raw_dir) as raw_dir:
        events = list(
            EventsHarvester(raw_dir=raw_dir).run(
                start_date=target_datetime,
                end_date=target_datetime,
                interval="15m",
                delete_raw=True,
                adm1_code=settings.target_adm1,
                actor_cameo=None,
                raise_on_download_error=True,
            )
        )
        if not events:
            return 0
        gkg = GkgHarvester(raw_dir=raw_dir).run(
            start_date=target_datetime,
            end_date=target_datetime,
            interval="15m",
            delete_raw=True,
            adm1_code=settings.target_adm1,
            raise_on_download_error=True,
        )
        try:
            return upload_to_elasticsearch(
                es_client,
                iter_joined_records(events, gkg, target_datetime),
                index_name=settings.es_index,
            )
        finally:
            gkg.close()
