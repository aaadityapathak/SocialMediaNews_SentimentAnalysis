import asyncio
from valkey.asyncio import Valkey

from base import setup_logging
from valkey_settings import ValkeySettings
from mastodon_retrieve import MastodonSettings
from base.read_fission_cfg import read_from_secret
from mastodon_retrieve.streamer import MastodonStreamer

setup_logging()


def mastodon_au():
    """
    Stream data from mastodon.au site
    """
    mast_settings = read_from_secret("mastodon-au", MastodonSettings)
    vk_settings = read_from_secret("valkey-cfg", ValkeySettings)
    vk_client = Valkey(host=vk_settings.host, port=vk_settings.port)
    mastodon_client = MastodonStreamer(settings=mast_settings)

    total = asyncio.run(
        mastodon_client.stream_to_vk(vk_client, max_time=30.0, local=True)
    )
    return {"total_added": total}


def au_social():
    """
    Stream data from au.social site
    """
    mast_settings = read_from_secret("mastodon-au-social", MastodonSettings)
    vk_settings = read_from_secret("valkey-cfg", ValkeySettings)
    vk_client = Valkey(host=vk_settings.host, port=vk_settings.port)
    mastodon_client = MastodonStreamer(settings=mast_settings)

    total = asyncio.run(
        mastodon_client.stream_to_vk(vk_client, max_time=30.0, local=True)
    )
    return {"total_added": total}


def mastodon_social():
    """
    Stream from the mastodon.social main server but only for specified hashtags
    :return:
    """
    mast_settings = read_from_secret("mastodon-social", MastodonSettings)
    vk_settings = read_from_secret("valkey-cfg", ValkeySettings)
    vk_client = Valkey(host=vk_settings.host, port=vk_settings.port)
    mastodon_client = MastodonStreamer(settings=mast_settings)

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

    async def gather_tag_posts() -> list[int]:
        totals = await asyncio.gather(
            *(
                mastodon_client.stream_to_vk(
                    vk_client, hashtag=tag, max_time=30.0, local=False
                )
                for tag in tags
            )
        )
        return totals

    counts = asyncio.run(gather_tag_posts())
    return {"total_added": sum(counts)}
