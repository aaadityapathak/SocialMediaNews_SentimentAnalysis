"""Streaming census records and bounded storage operations."""

import json
import logging
from itertools import batched
from pathlib import Path

from elasticsearch.helpers import streaming_bulk

from .process_census import (
    CENSUS_INDEX,
    CENSUS_QUEUE,
    detect_dataset,
    extract_record,
)

log = logging.getLogger(__name__)


def iter_shapefiles(data_dir: str, folders: str | None = None):
    root = Path(data_dir)
    if not root.is_dir():
        raise FileNotFoundError(f"Census directory does not exist: {root}")
    targets = (
        [root / f.strip() for f in folders.split(",") if f.strip()]
        if folders
        else [root, *sorted(p for p in root.iterdir() if p.is_dir())]
    )
    for folder in targets:
        yield from sorted(folder.glob("*.shp"))


def read_records(shp_path: Path):
    meta = detect_dataset(shp_path)
    if meta is None:
        return
    import geopandas as gpd

    zone_type, year = meta
    frame = gpd.read_file(shp_path).to_crs(epsg=4326)
    columns = list(frame.columns)
    for values in frame.itertuples(index=False, name=None):
        record = extract_record(
            dict(zip(columns, values)), columns, zone_type, year
        )
        if record["geometry"] is not None:
            yield record


def bulk_upsert(es, records, batch_size: int = 500) -> int:
    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    actions = (
        {
            "_op_type": "update",
            "_index": CENSUS_INDEX,
            "_id": record["_id"],
            "doc": {k: v for k, v in record.items() if k != "_id"},
            "doc_as_upsert": True,
        }
        for record in records
    )
    count = 0
    for ok, result in streaming_bulk(
        es, actions, chunk_size=batch_size, max_retries=3, raise_on_error=True
    ):
        if not ok:
            raise RuntimeError(f"Census bulk write failed: {result}")
        count += 1
    return count


def enqueue_records(vk, records, batch_size: int = 500) -> int:
    """One RPUSH per bounded batch; preserve the census queue's FIFO order."""
    count = 0
    for batch in batched(records, batch_size):
        vk.rpush(CENSUS_QUEUE, *(json.dumps(record) for record in batch))
        count += len(batch)
    return count
