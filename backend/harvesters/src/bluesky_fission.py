import asyncio
from valkey.asyncio import Valkey

from valkey_settings import ValkeySettings
from bluesky.settings import BlueskySettings
from bluesky.streamer import BlueskyStreamer
from base import setup_logging
from base.read_fission_cfg import read_from_secret

setup_logging()


def bluesky_stream():
    """
    Stream broadly AU-relevant data from Bluesky JetStream and store it in Elasticsearch.
    """
    vk_settings = read_from_secret("valkey-cfg", ValkeySettings)
    bs_settings = read_from_secret("bluesky-main", BlueskySettings)

    async def run_stream() -> int:
        async with Valkey(
            host=vk_settings.host, port=vk_settings.port
        ) as vk_client:
            bluesky_client = BlueskyStreamer(settings=bs_settings)
            return await bluesky_client.stream_to_vk(
                vk_client,
                max_time=30.0,
            )

    total = asyncio.run(run_stream())
    return {"total_added": total}
