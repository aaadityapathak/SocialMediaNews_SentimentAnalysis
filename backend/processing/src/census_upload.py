import json
import logging
from pathlib import Path

import fire
import geopandas as gpd
from valkey import Valkey

from base import setup_logging
from processing.process_census import (
    CENSUS_INDEX,
    CENSUS_QUEUE,
    detect_dataset,
    extract_record,
)

setup_logging()
log = logging.getLogger(__name__)


def _load_es_settings(env_file: str):
    from dotenv import load_dotenv
    from elastic import ESSettings

    load_dotenv(env_file)

    return ESSettings()


def _iter_shapefiles(data_dir: str, folders: str | None):
    root = Path(data_dir)
    targets = (
        [root / f.strip() for f in folders.split(",")]
        if folders
        else [p for p in root.iterdir() if p.is_dir()]
    )
    for folder in targets:
        shp_files = list(folder.glob("*.shp"))
        if not shp_files:
            log.warning("No .shp found in %s", folder)
        yield from shp_files


def _read_records(shp_path: Path):
    meta = detect_dataset(shp_path)
    if meta is None:
        return
    zone_type, year = meta
    gdf = gpd.read_file(shp_path).to_crs(epsg=4326)
    columns = list(gdf.columns)
    for _, row in gdf.iterrows():
        record = extract_record(row, columns, zone_type, year)
        if record["geometry"] is not None:
            yield record


def upload(
    data_dir: str = "data/census-data",
    folders: str | None = None,
    direct: bool = False,
    env_file: str = ".env",
    valkey_host: str = "localhost",
    valkey_port: int = 6379,
):
    if direct:
        from elasticsearch import Elasticsearch

        settings = _load_es_settings(env_file)
        es = Elasticsearch(
            settings.host, api_key=settings.api_key, verify_certs=False
        )
        total = 0
        for shp in _iter_shapefiles(data_dir, folders):
            count = 0
            for record in _read_records(shp):
                doc_id = record.pop("_id")
                es.update(
                    index=CENSUS_INDEX,
                    id=doc_id,
                    body={"doc": record, "doc_as_upsert": True},
                )
                count += 1
            log.info("Upserted %d records from %s", count, shp.name)
            total += count
        log.info("Done. Total upserted: %d", total)
        return {"upserted": total}
    else:
        vk = Valkey(host=valkey_host, port=valkey_port)
        total = 0
        for shp in _iter_shapefiles(data_dir, folders):
            count = 0
            for record in _read_records(shp):
                vk.rpush(CENSUS_QUEUE, json.dumps(record))
                count += 1
            log.info("Queued %d records from %s", count, shp.name)
            total += count
        log.info("Done. Total queued: %d", total)
        return {"queued": total}


if __name__ == "__main__":
    fire.Fire(upload)
