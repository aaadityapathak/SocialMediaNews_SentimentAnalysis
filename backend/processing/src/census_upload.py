"""CLI adapter for the census ingestion package."""

import logging

import fire
from base import setup_logging
from processing.census_io import (
    bulk_upsert,
    enqueue_records,
)
from processing.census_io import (
    iter_shapefiles as _iter_shapefiles,
)
from processing.census_io import (
    read_records as _read_records,
)
from valkey import Valkey

log = logging.getLogger(__name__)


def _load_es_settings(env_file: str):
    from dotenv import load_dotenv
    from elastic import ESSettings

    load_dotenv(env_file)
    return ESSettings()


def upload(
    data_dir: str = "data/census-data",
    folders: str | None = None,
    direct: bool = False,
    env_file: str = ".env",
    valkey_host: str = "localhost",
    valkey_port: int = 6379,
    batch_size: int = 500,
):
    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    if direct:
        from elasticsearch import Elasticsearch

        settings = _load_es_settings(env_file)
        client = Elasticsearch(
            settings.host, api_key=settings.api_key, verify_certs=False
        )
    else:
        client = Valkey(host=valkey_host, port=valkey_port)
    total = 0
    try:
        for shp in _iter_shapefiles(data_dir, folders):
            records = _read_records(shp)
            count = (bulk_upsert if direct else enqueue_records)(
                client, records, batch_size
            )
            log.info(
                "%s %d records from %s",
                "Upserted" if direct else "Queued",
                count,
                shp.name,
            )
            total += count
    finally:
        client.close()
    return {"upserted" if direct else "queued": total}


if __name__ == "__main__":
    setup_logging()
    fire.Fire(upload)
