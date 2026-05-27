import fire
from elasticsearch import AsyncElasticsearch

from elastic import ESSettings
from base import setup_logging
from .streamer import BlueskyStreamer

setup_logging()


async def stream_records(
    max_runtime: float = 240.0,
    keywords: str | None = None,
):
    """
    Stream AU-relevant Bluesky posts to Elasticsearch.

    keywords is optional and is used as an additional topic filter only.
    """
    streamer = BlueskyStreamer()

    es_settings = ESSettings()
    keyword_list = None
    if keywords:
        keyword_list = list(filter(None, map(str.strip, keywords.split(";"))))

    async with AsyncElasticsearch(
        es_settings.host,
        api_key=es_settings.api_key,
        verify_certs=False,
    ) as es:
        total = await streamer.stream_to_vk(
            es,
            queue="bluesky-idx",
            max_time=max_runtime,
            keywords=keyword_list,
        )
    return {"total_added": total}


if __name__ == "__main__":
    fire.Fire({"stream": stream_records})
