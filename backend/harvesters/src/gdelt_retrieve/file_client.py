"""Bounded, reusable HTTP downloads and streaming ZIP readers for GDELT."""

from __future__ import annotations

import csv
import hashlib
import io
import logging
import sys
import tempfile
import zipfile
from collections.abc import Iterator
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .gdelt_harvest import GdeltFileSpec

_field_limit = sys.maxsize
while True:
    try:
        csv.field_size_limit(_field_limit)
        break
    except OverflowError:
        _field_limit //= 10

CHUNK_SIZE = 256 * 1024
REQUEST_TIMEOUT = (10, 120)


def create_session() -> requests.Session:
    """Reuse connections and retry transient failures on safe GET requests."""
    session = requests.Session()
    retries = Retry(
        total=3,
        backoff_factor=0.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET"}),
    )
    adapter = HTTPAdapter(max_retries=retries)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


class GdeltFileClient:
    """Cache complete archives atomically and close connections deterministically."""

    def __init__(self, raw_dir: Path, session=None) -> None:
        self.raw_dir = Path(raw_dir)
        self.logger = logging.getLogger("gdelt.file_client")
        self.session = session if session is not None else create_session()
        self._owns_session = session is None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def close(self):
        if self._owns_session:
            self.session.close()

    def ensure_downloaded(
        self, spec: GdeltFileSpec, date_str: str, skip_existing: bool = True
    ) -> tuple[Path, bool]:
        date_dir = self.raw_dir / date_str
        date_dir.mkdir(parents=True, exist_ok=True)
        dest = date_dir / spec.filename(date_str)
        if skip_existing and dest.is_file() and zipfile.is_zipfile(dest):
            return dest, True
        success, _ = self._stream_download(spec.url(date_str), dest, spec.label)
        return dest, success

    def _stream_download(
        self, url: str, dest: Path, label: str
    ) -> tuple[bool, str | None]:
        # A failed refresh must never overwrite an existing complete archive.
        temporary = None
        digest = hashlib.md5(usedforsecurity=False)
        try:
            with self.session.get(
                url, stream=True, timeout=REQUEST_TIMEOUT
            ) as response:
                response.raise_for_status()
                with tempfile.NamedTemporaryFile(
                    dir=dest.parent,
                    prefix=dest.name + ".",
                    suffix=".part",
                    delete=False,
                ) as output:
                    temporary = Path(output.name)
                    for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
                        if chunk:
                            output.write(chunk)
                            digest.update(chunk)
            if not zipfile.is_zipfile(temporary):
                raise zipfile.BadZipFile(
                    "Downloaded response is not a ZIP archive"
                )
            temporary.replace(dest)
            return True, digest.hexdigest()
        except (requests.RequestException, OSError, zipfile.BadZipFile) as exc:
            self.logger.error(
                "[%s] Download failed for %s: %s", label, url, exc
            )
            return False, None
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def iter_rows(self, zip_path: Path) -> Iterator[list[str]]:
        with zipfile.ZipFile(zip_path) as archive:
            for member in archive.infolist():
                if member.is_dir():
                    continue
                with (
                    archive.open(member) as raw,
                    io.TextIOWrapper(
                        raw, encoding="utf-8", errors="replace", newline=""
                    ) as source,
                ):
                    yield from csv.reader(source, delimiter="\t")
