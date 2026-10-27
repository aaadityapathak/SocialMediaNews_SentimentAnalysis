"""Local polling entry point using the same ingestion pipeline as Fission."""

import logging
import time

from elastic.settings import ESSettings
from elasticsearch import Elasticsearch
from gdelt_retrieve.settings import GdeltStreamSettings
from gdelt_retrieve.streamer import (
    get_latest_gdelt_timestamp,
)
from gdelt_retrieve.streamer import (
    process_and_stream_batch as _process_batch,
)

logger = logging.getLogger(__name__)


def process_and_stream_batch(target_datetime, settings):
    es_settings = ESSettings()
    with Elasticsearch(
        es_settings.host, api_key=es_settings.api_key, verify_certs=False
    ) as client:
        return _process_batch(target_datetime, settings, client)


def main():
    settings = GdeltStreamSettings()
    last_processed = None
    while True:
        latest = get_latest_gdelt_timestamp(settings.update_url)
        if latest and (last_processed is None or latest > last_processed):
            try:
                process_and_stream_batch(latest, settings)
            except Exception:
                logger.exception(
                    "GDELT batch failed; retrying on the next poll"
                )
            else:
                last_processed = latest
        time.sleep(settings.poll_interval_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
