"""Shared bounded Threads orchestration for local and Fission entry points."""

import concurrent.futures
import logging
import threading
import time
from dataclasses import dataclass

from elasticsearch import Elasticsearch

from . import scrape_keyword
from .schemas import make_document, upload_to_elasticsearch
from .settings import ThreadsStreamSettings

logger = logging.getLogger(__name__)


def get_es_client(settings: ThreadsStreamSettings) -> Elasticsearch:
    if not settings.elastic_api_key:
        raise ValueError("Missing ELASTIC_API_KEY")
    return Elasticsearch(
        settings.elastic_host,
        api_key=settings.elastic_api_key,
        verify_certs=False,
    )


def _collect(keyword, stop_event, settings, deadline):
    if stop_event.is_set() or time.monotonic() >= deadline:
        return []
    posts, blocked = scrape_keyword(
        keyword,
        stop_event=stop_event,
        deadline=deadline,
        timeout_seconds=settings.keyword_timeout_seconds,
        max_scrolls=settings.max_scrolls,
    )
    if blocked:
        stop_event.set()
    return [
        make_document(post, keyword)
        for post in posts
        if post.get("text") and post.get("id")
    ]


def process_keyword(keyword, stop_event, doc_list, list_lock):
    """Compatibility worker for existing callers."""
    settings = ThreadsStreamSettings()
    documents = _collect(
        keyword,
        stop_event,
        settings,
        time.monotonic() + settings.keyword_timeout_seconds,
    )
    with list_lock:
        doc_list.extend(documents)


@dataclass(frozen=True)
class HarvestResult:
    total_added: int
    interrupted: bool


def harvest_keywords(es_client, settings, keywords=None) -> HarvestResult:
    """Keep at most ``max_workers`` keyword tasks in flight.

    Each task still returns a page's parsed payload. Completed payloads are
    released after upload; only post IDs are retained for cross-keyword dedup.
    """
    keywords = list(
        dict.fromkeys(settings.keywords if keywords is None else keywords)
    )
    stop_event = threading.Event()
    deadline = time.monotonic() + settings.harvest_timeout_seconds
    seen = set()
    total = 0
    errors = []
    with concurrent.futures.ThreadPoolExecutor(
        max_workers=settings.max_workers
    ) as executor:
        keyword_iter = iter(keywords)
        pending = set()

        def refill():
            # Keep at most max_workers futures in flight. Submitting all
            # keywords at once also retains every completed payload in the
            # original future list, even after its documents were indexed.
            while (
                len(pending) < settings.max_workers and not stop_event.is_set()
            ):
                if time.monotonic() >= deadline:
                    stop_event.set()
                    break
                keyword = next(keyword_iter, None)
                if keyword is None:
                    break
                pending.add(
                    executor.submit(
                        _collect, keyword, stop_event, settings, deadline
                    )
                )

        refill()
        while pending:
            completed, pending = concurrent.futures.wait(
                pending, return_when=concurrent.futures.FIRST_COMPLETED
            )
            for future in completed:
                try:
                    documents = future.result()
                    unique = []
                    for document in documents:
                        post_id = str(document["post_id"])
                        if post_id not in seen:
                            seen.add(post_id)
                            unique.append(document)
                    if unique:
                        total += upload_to_elasticsearch(
                            es_client, unique, settings.es_index
                        )
                except Exception as exc:  # noqa: BLE001 - aggregate worker/upload failures
                    stop_event.set()
                    errors.append(exc)
            # Drop completed futures before scheduling their replacements.
            completed.clear()
            refill()
        if time.monotonic() >= deadline:
            stop_event.set()
    if errors:
        raise RuntimeError(
            f"Threads harvest failed in {len(errors)} workers or uploads"
        ) from errors[0]
    return HarvestResult(total, stop_event.is_set())


def run_stream():
    settings = ThreadsStreamSettings()
    with get_es_client(settings) as client:
        result = harvest_keywords(client, settings)
    logger.info(
        "Indexed %s Threads posts; interrupted=%s",
        result.total_added,
        result.interrupted,
    )
    return result
