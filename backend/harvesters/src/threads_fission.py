"""Fission entry point sharing the local Threads ingestion pipeline."""

import random

from base.read_fission_cfg import read_from_secret
from elastic.settings import ESSettings
from elasticsearch import Elasticsearch
from threads_retrieve.settings import ThreadsStreamSettings
from threads_retrieve.streamer import harvest_keywords


def threads_harvest():
    settings = ThreadsStreamSettings()
    keywords = list(dict.fromkeys(settings.keywords))
    targets = random.sample(
        keywords, min(settings.fission_keyword_limit, len(keywords))
    )
    credentials = read_from_secret("elastic-api-credentials", ESSettings)
    with Elasticsearch(
        credentials.host, api_key=credentials.api_key, verify_certs=False
    ) as client:
        result = harvest_keywords(client, settings, targets)
    return {
        "status": "interrupted" if result.interrupted else "success",
        "total_added": result.total_added,
    }
