"""
Youtube retrieval test. Run this to fetch records from youtube. Run this script to fetch some records. Development Only.
"""

import json
import logging
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path

import fire
from base import setup_logging
from valkey import Valkey
from valkey_settings import ValkeySettings

from .defaults import SEARCH_QUERIES
from .streamer import YoutubeStreamer
from .youtube import YoutubeHarvester

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

    with (
        open(save_to, "w", encoding="utf-8") as f,
        closing(harvester.run(start_time, end_time, queries=queries)) as videos,
    ):
        f.writelines(json.dumps(video) + "\n" for video in videos)

    log.info("Saved %s records to %s", "youtube", save_to)


def stream(
    start_time: datetime = _defaults[0],
    end_time: datetime = _defaults[1],
    query: str | None = None,
):
    """
    Fetch YouTube records and enqueue them in Valkey for processing.
    Requires YOUTUBE_API_KEY and the Valkey connection settings.
    :param start_time: Start of the harvest window (ISO datetime)
    :param end_time: End of the harvest window (ISO datetime)
    :param query: JSON string mapping topic to list of search queries
    """
    queries = json.loads(query) if query else None
    vk_settings = ValkeySettings()
    vk = Valkey(host=vk_settings.host, port=vk_settings.port)

    streamer = YoutubeStreamer()
    try:
        counts = streamer.harvest_to_vk(
            vk, start_time, end_time, queries=queries
        )
    finally:
        vk.close()
    log.info("Sending to Valkey Queue: %s", counts)


if __name__ == "__main__":
    fire.Fire({"gather": gather, "stream": stream})
