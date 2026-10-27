import fire
from valkey.asyncio import Valkey

from valkey_settings import ValkeySettings
from base import setup_logging
from .streamer import BlueskyStreamer

setup_logging()


async def stream_records(
    max_runtime: float = 240.0,
    keywords: str | None = None,
):
    """
    Stream AU-relevant Bluesky posts to the processing queue.

    keywords is optional and is used as an additional topic filter only.
    """
    streamer = BlueskyStreamer()

    vk_settings = ValkeySettings()
    keyword_list = None
    if keywords:
        keyword_list = list(filter(None, map(str.strip, keywords.split(";"))))

    async with Valkey(host=vk_settings.host, port=vk_settings.port) as vk:
        total = await streamer.stream_to_vk(
            vk,
            queue="social-posts-index",
            max_time=max_runtime,
            keywords=keyword_list,
        )
    return {"total_added": total}


if __name__ == "__main__":
    fire.Fire({"stream": stream_records})
