"""Import GDELT CSV backups with bounded memory and shared normalization."""

import argparse
import csv
import logging
from contextlib import ExitStack, closing
from datetime import datetime
from decimal import Decimal, InvalidOperation
from itertools import batched, chain
from pathlib import Path

from elastic.settings import ESSettings
from elasticsearch import Elasticsearch

from .schemas import USEFUL_COLUMNS, upload_to_elasticsearch

logger = logging.getLogger(__name__)


def _integer_text(value: str) -> str:
    number = Decimal(value)
    if (
        not number.is_finite()
        or number < 0
        or number != number.to_integral_value()
    ):
        raise ValueError("expected a non-negative integer")
    return str(int(number))


def iter_backup_rows(file_path):
    """Read one CSV row at a time, including legacy pandas float timestamps."""
    with Path(file_path).open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        if not reader.fieldnames or not {"GlobalEventID", "SourceURL"}.issubset(
            reader.fieldnames
        ):
            raise ValueError(
                "Backup requires GlobalEventID and SourceURL columns"
            )
        columns = [name for name in USEFUL_COLUMNS if name in reader.fieldnames]
        for row in reader:
            if None in row:
                raise ValueError(
                    f"Unexpected extra CSV columns at line {reader.line_num}"
                )
            record = {
                name: None
                if row[name] is None or row[name].strip().lower() in {"", "nan"}
                else row[name].strip()
                for name in columns
            }
            try:
                if not record["GlobalEventID"] or not record["SourceURL"]:
                    raise ValueError(
                        "GlobalEventID and SourceURL must not be empty"
                    )
                record["GlobalEventID"] = _integer_text(record["GlobalEventID"])
                if record.get("DateAdded"):
                    timestamp = _integer_text(record["DateAdded"])
                    if len(timestamp) not in {8, 14}:
                        raise ValueError(
                            "DateAdded must contain 8 or 14 digits"
                        )
                    timestamp = timestamp.ljust(14, "0")
                    datetime.strptime(timestamp, "%Y%m%d%H%M%S")
                    record["DateAdded"] = timestamp
            except (ValueError, InvalidOperation) as exc:
                raise ValueError(
                    f"Invalid GDELT backup record at line {reader.line_num}: {exc}"
                ) from exc
            yield record


def import_backup(
    file_path, *, index_name: str, batch_size: int = 500, es_client=None
) -> int:
    """Index each CSV batch before reading more, propagating any failed writes."""
    if not isinstance(batch_size, int) or batch_size < 1:
        raise ValueError("batch_size must be a positive integer")
    if not isinstance(index_name, str) or not index_name.strip():
        raise ValueError("index_name must not be empty")
    with ExitStack() as stack:
        rows = stack.enter_context(closing(iter_backup_rows(file_path)))
        batches = batched(rows, batch_size)
        first = next(batches, ())
        if not first:
            return 0
        if es_client is None:
            settings = ESSettings()
            es_client = stack.enter_context(
                Elasticsearch(
                    settings.host,
                    api_key=settings.api_key,
                    verify_certs=False,
                    request_timeout=120,
                )
            )
        total = 0
        for batch in chain((first,), batches):
            total += upload_to_elasticsearch(es_client, batch, index_name)
        return total


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file_path", type=Path, help="CSV backup to import")
    parser.add_argument("--index", dest="index_name", required=True)
    parser.add_argument("--batch-size", type=int, default=500)
    options = vars(parser.parse_args())
    logging.basicConfig(level=logging.INFO)
    logger.info("Indexed %s GDELT backup documents", import_backup(**options))
