"""
handles all HTTP download and zip I/O for GDELT v1.0 and v2.0 files.
"""

from __future__ import annotations

import csv
import hashlib
import io
import logging
import zipfile
import sys
from pathlib import Path
from typing import Iterator

import requests

from .gdelt_harvest import GdeltFileSpec, get_logger

maxInt = sys.maxsize
while True:
    try:
        csv.field_size_limit(maxInt)
        break
    except OverflowError:
        maxInt = int(maxInt / 10)

CHUNK_SIZE = 256 * 1024
REQUEST_TIMEOUT = 120


class GdeltFileClient:
    """Manages idempotent downloads and stream reading for large zipped datasets."""

    def __init__(self, raw_dir: Path) -> None:
        """
        Parameters
        ----------
        raw_dir : Path
            The local directory for storing/finding cached zip files.
        """
        self.raw_dir = raw_dir
        self.logger: logging.Logger = get_logger("gdelt.file_client")

    def ensure_downloaded(
        self,
        spec: GdeltFileSpec,
        date_str: str,
        skip_existing: bool = True,
    ) -> tuple[Path, bool]:
        """
        Guarantees the required data file is present locally, downloading if necessary.

        Parameters
        ----------
        spec : GdeltFileSpec
            Specification dictating the URL and naming convention.
        date_str : str
            Target date 'YYYYMMDD'.
        skip_existing : bool, optional
            If True, skips network requests if the file exists on disk. Defaults to True.

        Returns
        -------
        tuple[Path, bool]
            (Path_to_file, Success_flag)
        """
        date_dir = self.raw_dir / date_str
        date_dir.mkdir(parents=True, exist_ok=True)

        dest = date_dir / spec.filename(date_str)

        if skip_existing and dest.exists():
            self.logger.info(
                f"[{spec.label}] Cache hit — skipping download: {dest.name}"
            )
            return dest, True

        url = spec.url(date_str)
        self.logger.info(f"[{spec.label}] Downloading: {url}")

        success, md5_hash = self._stream_download(url, dest, spec.label)
        if success:
            self.logger.info(
                f"[{spec.label}] Saved {dest.stat().st_size / 1e6:.1f} MB "
                f"→ {dest.name}  (md5={md5_hash})"
            )
        return dest, success

    def _stream_download(
        self, url: str, dest: Path, label: str
    ) -> tuple[bool, str | None]:
        """
        Streams a file over HTTP to disk in chunks, simultaneously computing its MD5 hash.

        Parameters
        ----------
        url : str
        dest : Path Local destination
        label : str for console logging.

        Returns
        -------
        tuple[bool, str | None]
            (True, MD5_String) on success; (False, None) on failure.
        """
        h = hashlib.md5()
        try:
            resp = requests.get(url, stream=True, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            with open(dest, "wb") as fh:
                for chunk in resp.iter_content(chunk_size=CHUNK_SIZE):
                    if chunk:
                        fh.write(chunk)
                        # Hash is computed during the disk write loop to save I/O overhead
                        h.update(chunk)
            return True, h.hexdigest()

        except requests.exceptions.HTTPError as exc:
            self.logger.error(
                f"[{label}] HTTP {exc.response.status_code}: {url}"
            )
        except requests.exceptions.Timeout:
            self.logger.error(
                f"[{label}] Timed out after {REQUEST_TIMEOUT}s: {url}"
            )
        except requests.exceptions.ConnectionError as exc:
            self.logger.error(f"[{label}] Connection error: {exc}")
        except Exception as exc:
            self.logger.error(f"[{label}] Unexpected error: {exc}")

        # Clean up any corrupted/partial files on failure
        if dest.exists():
            dest.unlink()
            self.logger.warning(f"[{label}] Partial file removed: {dest.name}")
        return False, None

    def iter_rows(self, zip_path: Path) -> Iterator[list[str]]:
        """
        Streams CSV rows directly from an unopened ZIP file via a TextIOWrapper.

        Parameters
        ----------
        zip_path : Path to the local ZIP file.

        Yields
        ------
        Iterator[list[str]]
            Streams parsed rows representing individual cells.
        """
        with zipfile.ZipFile(zip_path, "r") as zf:
            inner_names = zf.namelist()
            if not inner_names:
                self.logger.error(f"Empty zip file: {zip_path.name}")
                return

            inner_name = inner_names[0]
            with zf.open(inner_name) as raw:
                reader = csv.reader(
                    io.TextIOWrapper(raw, encoding="utf-8", errors="replace"),
                    delimiter="\t",
                )
                yield from reader
