"""Fission entry point for one GDELT update."""

import logging

from base.read_fission_cfg import read_from_secret
from elastic.settings import ESSettings
from elasticsearch import Elasticsearch
from gdelt_retrieve.settings import GdeltStreamSettings
from gdelt_retrieve.streamer import (
    get_latest_gdelt_timestamp,
    process_and_stream_batch,
)

logger = logging.getLogger(__name__)


def harvest_latest_gdelt():
    settings = GdeltStreamSettings()
    latest_time = get_latest_gdelt_timestamp(settings.update_url)
    if latest_time is None:
        raise RuntimeError("Could not fetch the latest GDELT timestamp")
    es_settings = read_from_secret("elastic-api-credentials", ESSettings)
    with Elasticsearch(
        es_settings.host, api_key=es_settings.api_key, verify_certs=False
    ) as client:
        count = process_and_stream_batch(latest_time, settings, client)
    return {
        "status": "success",
        "batch_time": str(latest_time),
        "total_added": count,
    }
