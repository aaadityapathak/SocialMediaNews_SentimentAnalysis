import logging
import random
import threading
import concurrent.futures
from elasticsearch import Elasticsearch

from base import setup_logging
from base.read_fission_cfg import read_from_secret
from elastic.settings import ESSettings
from threads_retrieve.settings import ThreadsStreamSettings
from threads_retrieve.streamer import process_keyword
from threads_retrieve.schemas import upload_to_elasticsearch

setup_logging()
logger = logging.getLogger(__name__)


def threads_harvest():
    """
    Fission entrypoint for Threads.
    Processes a random subset of keywords to ensure completion within the timeout.
    """
    logger.info("Threads Fission function triggered.")

    # 1. Read ES credentials from the existing K8s secret
    es_settings = read_from_secret("elastic-api-credentials", ESSettings)
    es_client = Elasticsearch(
        es_settings.host, api_key=es_settings.api_key, verify_certs=False
    )

    # 2. Select 5 random keywords from your refined Australian list
    settings = ThreadsStreamSettings()
    target_keywords = random.sample(
        settings.keywords, min(5, len(settings.keywords))
    )

    all_documents = []
    list_lock = threading.Lock()
    stop_event = threading.Event()

    # 3. Parallel execution with staggered starts to avoid browser crashes
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        futures = [
            executor.submit(
                process_keyword, kw, stop_event, all_documents, list_lock
            )
            for kw in target_keywords
        ]
        # Wait for completion or a 90s safety timeout
        concurrent.futures.wait(futures, timeout=90)

    # 4. Final Bulk Upload to Elasticsearch
    if all_documents:
        success = upload_to_elasticsearch(
            es_client, all_documents, index_name=settings.es_index
        )
        logger.info(f"Indexed {success} posts.")
        return {"status": "success", "total_added": success}

    return {"status": "no_data_or_blocked"}
