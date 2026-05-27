import logging
from elasticsearch import Elasticsearch

# Adjust import paths based on your actual project structure
from base.read_fission_cfg import read_from_secret
from elastic.settings import ESSettings
from gdelt_retrieve.settings import GdeltStreamSettings
from gdelt_retrieve.streamer import (
    get_latest_gdelt_timestamp,
    process_and_stream_batch,
)

# Setup basic logging for Fission router
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)


def harvest_latest_gdelt():
    """
    Fission entrypoint to fetch and process the latest 15m GDELT batch.
    Designed to be triggered by a Fission Time Trigger (e.g., cron every 15 mins).
    """
    logger.info("GDELT Fission function triggered.")

    # 1. Read Elasticsearch credentials from K8s secret mounted by Fission
    es_settings = read_from_secret("elastic-api-credentials", ESSettings)

    # 2. Instantiate the ES Client here so we don't rely on local .env files
    es_client = Elasticsearch(
        es_settings.host, api_key=es_settings.api_key, verify_certs=False
    )

    # 3. Load GDELT default configurations (Targeting Victoria)
    gdelt_settings = GdeltStreamSettings()

    # 4. Ping GDELT server for the latest available 15-minute batch
    latest_time = get_latest_gdelt_timestamp(gdelt_settings.update_url)

    if not latest_time:
        logger.error(
            "Could not fetch latest GDELT timestamp from lastupdate.txt"
        )
        return {"status": "error", "message": "Timestamp fetch failed"}

    logger.info(f"Latest global GDELT batch identified: {latest_time}")

    # 5. Process the batch and push to ES
    # Note: If Fission accidentally triggers twice for the same batch, Elasticsearch
    # handles the deduplication automatically based on the unique ID.
    processed_count = process_and_stream_batch(
        latest_time, gdelt_settings, es_client
    )

    return {
        "status": "success",
        "batch_time": str(latest_time),
        "total_added": processed_count,
    }
