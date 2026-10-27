"""Shared date iteration and archive lifecycle for GDELT source adapters."""

from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zipfile import BadZipFile

from .file_client import GdeltFileClient


def iter_archive_rows(
    raw_dir,
    start_date,
    end_date,
    interval,
    daily_spec,
    quarter_hour_spec,
    *,
    delete_raw=False,
    skip_existing=True,
    raise_on_download_error=False,
):
    if interval not in {"daily", "15m"}:
        raise ValueError("interval must be 'daily' or '15m'")

    def utc(value: datetime):
        return (
            value.astimezone(UTC).replace(tzinfo=None)
            if value.tzinfo
            else value
        )

    start, end = utc(start_date), utc(end_date)
    if start > end:
        raise ValueError("start_date must not be after end_date")
    if interval == "15m":
        current = start.replace(
            minute=start.minute // 15 * 15, second=0, microsecond=0
        )
        spec, step, date_format = (
            quarter_hour_spec,
            timedelta(minutes=15),
            "%Y%m%d%H%M%S",
        )
    else:
        current = start.replace(hour=0, minute=0, second=0, microsecond=0)
        spec, step, date_format = daily_spec, timedelta(days=1), "%Y%m%d"
    with GdeltFileClient(Path(raw_dir)) as client:
        while current <= end:
            date_str = current.strftime(date_format)
            archive, success = client.ensure_downloaded(
                spec, date_str, skip_existing
            )
            if not success:
                if raise_on_download_error:
                    raise OSError(
                        f"Could not download GDELT archive {spec.filename(date_str)}"
                    )
                current += step
                continue
            try:
                with closing(client.iter_rows(archive)) as rows:
                    yield from rows
            except BadZipFile:
                # CRC/stream corruption can only be detected while reading.
                # Remove the invalid cache so the next run downloads it again.
                archive.unlink(missing_ok=True)
                raise
            finally:
                if delete_raw:
                    archive.unlink(missing_ok=True)
            current += step
