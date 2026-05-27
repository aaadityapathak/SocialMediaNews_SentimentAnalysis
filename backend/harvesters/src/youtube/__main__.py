"""
Youtube retrieval test. Run this to fetch records from youtube. Run this script to fetch some records. Development Only.
"""

import json
import logging
import fire

from pathlib import Path
from datetime import datetime, UTC, timedelta
from valkey import Valkey

from base import setup_logging
from valkey_settings import ValkeySettings
from .youtube import YoutubeHarvester
from .streamer import YoutubeStreamer
from .defaults import SEARCH_QUERIES

setup_logging(logging.DEBUG)
log = logging.getLogger(__name__)

out_path = Path(__file__).parents[2] / "youtube-data.jsonl"
_defaults = (datetime.now(UTC) - timedelta(days=30), datetime.now(UTC))


def gather(
    start_time: datetime = _defaults[0],
    end_time: datetime = _defaults[1],
    save_to: str | Path = out_path,
    query: str | None = None,
):
    """
    Fetch YouTube records and save them to a JSONL file.
    :param start_time: Start of the harvest window (ISO datetime)
    :param end_time: End of the harvest window (ISO datetime)
    :param save_to: Output file path
    :param query: JSON string mapping topic to list of search queries, e.g.
                  '{"weather": ["australia floods", "melbourne heatwave"]}'
    """
    queries = json.loads(query) if query else SEARCH_QUERIES
    harvester = YoutubeHarvester()

    with open(save_to, "w") as f:
        for video in harvester.run(start_time, end_time, queries=queries):
            f.write(json.dumps(video) + "\n")

    log.info("Saved %s records to %s", "youtube", save_to)


def stream(
    start_time: datetime = _defaults[0],
    end_time: datetime = _defaults[1],
    query: str | None = None,
):
    """
    Fetch YouTube records and index them directly into ElasticSearch across
    three indices: youtube-videos-idx, youtube-comments-idx, youtube-replies-idx.
    Requires ELASTIC_HOST and ELASTIC_API_KEY in the environment.
    :param start_time: Start of the harvest window (ISO datetime)
    :param end_time: End of the harvest window (ISO datetime)
    :param query: JSON string mapping topic to list of search queries
    """
    queries = json.loads(query) if query else None
    vk_settings = ValkeySettings()
    vk = Valkey(host=vk_settings.host, port=vk_settings.port)

    streamer = YoutubeStreamer()
    counts = streamer.harvest_to_vk(vk, start_time, end_time, queries=queries)
    log.info("Sending to Valkey Queue: %s", counts)


fire.Fire({"gather": gather, "stream": stream})
