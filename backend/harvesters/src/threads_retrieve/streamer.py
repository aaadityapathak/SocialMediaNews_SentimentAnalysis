import urllib3
import time
import random
import logging
import warnings
import threading
import concurrent.futures
from elasticsearch import Elasticsearch
from elasticsearch.exceptions import ElasticsearchWarning
from .settings import ThreadsStreamSettings
from . import scrape_keyword
from .schemas import make_document, upload_to_elasticsearch

warnings.simplefilter("ignore", ElasticsearchWarning)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger("threads_streamer")


def get_es_client(settings: ThreadsStreamSettings) -> Elasticsearch:
    if not settings.elastic_api_key:
        logger.error("ELASTIC_API_KEY is missing from your .env file!")
        raise ValueError("Missing API Key")

    return Elasticsearch(
        settings.elastic_host,
        api_key=settings.elastic_api_key,
        verify_certs=False,
    )


def process_keyword(
    keyword: str,
    stop_event: threading.Event,
    doc_list: list,
    list_lock: threading.Lock,
):
    """Parallel worker function that checks for stop signals."""
    # If another thread already got blocked, don't even start this search
    if stop_event.is_set():
        return

    try:
        # Stagger browser launches slightly to avoid Playwright crashes
        time.sleep(random.uniform(0.5, 3.0))

        # Double check stop event after sleep
        if stop_event.is_set():
            return

        logger.info(f"Searching: {keyword}")
        posts, is_blocked = scrape_keyword(keyword)

        # EMERGENCY STOP TRIGGER
        if is_blocked:
            logger.warning(
                f"Block detected on '{keyword}'. Signaling all threads to abort..."
            )
            stop_event.set()
            return

        if not posts:
            logger.info(f"No posts found for '{keyword}'")
            return

        # Map and filter documents
        docs = [make_document(p, keyword) for p in posts]
        valid_docs = [d for d in docs if d.get("text") and d.get("post_id")]

        # Thread-safe append to the master list
        if valid_docs:
            with list_lock:
                doc_list.extend(valid_docs)
                logger.info(f"Queued {len(valid_docs)} posts for '{keyword}'.")

    except Exception as e:
        logger.error(f"Error processing '{keyword}': {str(e)}")


def run_stream():
    settings = ThreadsStreamSettings()
    es_client = get_es_client(settings)

    # Shared thread variables
    all_documents = []
    list_lock = threading.Lock()
    stop_event = threading.Event()

    # Keep workers low (3-5) to give Stealth a fighting chance
    MAX_WORKERS = 4

    logger.info(
        f"Starting PARALLEL harvest for {len(settings.keywords)} keywords with {MAX_WORKERS} workers..."
    )

    # Run in parallel
    with concurrent.futures.ThreadPoolExecutor(
        max_workers=MAX_WORKERS
    ) as executor:
        futures = [
            executor.submit(
                process_keyword, keyword, stop_event, all_documents, list_lock
            )
            for keyword in settings.keywords
        ]
        # Wait for all submitted tasks to either finish or abort
        concurrent.futures.wait(futures)

    # ---------------------------------------------------------
    # FINAL STEP: Push whatever we successfully gathered to ES
    # ---------------------------------------------------------
    if stop_event.is_set():
        logger.warning("Harvest was interrupted by a Meta IP block.")

    if all_documents:
        logger.info(
            f"Bulk uploading {len(all_documents)} salvaged documents to Elasticsearch..."
        )
        success = upload_to_elasticsearch(
            es_client, all_documents, index_name=settings.es_index
        )
        logger.info(
            f"Successfully indexed {success} out of {len(all_documents)} posts!"
        )
    else:
        logger.warning(
            "No valid posts were gathered before the block. Nothing to upload."
        )

    logger.info("Job Exited.")
