import asyncio
from valkey.asyncio import Valkey

from base import setup_logging
from valkey_settings import ValkeySettings
from mastodon_retrieve import MastodonSettings
from base.read_fission_cfg import read_from_secret
from mastodon_retrieve.streamer import MastodonStreamer

setup_logging()


def _stream_instance(secret: str, tags: list[str] | None = None):
    """Keep the queue connection inside the event loop that owns it."""
    mast_settings = read_from_secret(secret, MastodonSettings)
    vk_settings = read_from_secret("valkey-cfg", ValkeySettings)
    streamer = MastodonStreamer(settings=mast_settings)

    async def run():
        async with Valkey(host=vk_settings.host, port=vk_settings.port) as vk:
            if not tags:
                return await streamer.stream_to_vk(
                    vk, max_time=30.0, local=True
                )
            # TaskGroup cancels and awaits sibling streams before closing vk
            # when one of the upstream subscriptions fails.
            async with asyncio.TaskGroup() as group:
                tasks = [
                    group.create_task(
                        streamer.stream_to_vk(
                            vk, hashtag=tag, max_time=30.0, local=False
                        )
                    )
                    for tag in tags
                ]
            return sum(task.result() for task in tasks)

    return {"total_added": asyncio.run(run())}


def mastodon_au():
    return _stream_instance("mastodon-au")


def au_social():
    return _stream_instance("mastodon-au-social")


def mastodon_social():
    """Stream Australia-related hashtags from mastodon.social."""
    tags = [
        "australia",
        "victoria",
        "melbourne",
        "sydney",
        "nsw",
        "canberra",
        "adelaide",
        "brisbane",
        "southaustralia",
        "westernaustralia",
        "auspol",
        "straya",
    ]

    return _stream_instance("mastodon-social", tags)
