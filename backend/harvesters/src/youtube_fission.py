# Team 23 — COMP90024 — YouTube Fission Harvester
from datetime import UTC, datetime, timedelta

from base import setup_logging
from base.read_fission_cfg import read_from_secret
from valkey import Valkey
from valkey_settings import ValkeySettings
from youtube.settings import YoutubeSettings
from youtube.streamer import YoutubeStreamer

setup_logging()


def youtube_harvest():
    """
    Harvest the last 12 hours of YouTube data and enqueue it for processing.
    """
    vk_settings = read_from_secret("valkey-cfg", ValkeySettings)
    yt_settings = read_from_secret("youtube-api-credentials", YoutubeSettings)

    vk = Valkey(host=vk_settings.host, port=vk_settings.port)

    end = datetime.now(UTC)
    start = end - timedelta(hours=12)

    streamer = YoutubeStreamer(settings=yt_settings)
    try:
        counts = streamer.harvest_to_vk(vk, start, end)
    finally:
        vk.close()

    return {**counts, "start": start.isoformat(), "end": end.isoformat()}
