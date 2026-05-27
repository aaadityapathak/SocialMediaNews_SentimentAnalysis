import re
import time
import json
import httpx
import logging
from functools import partial
from typing import AsyncIterator
from valkey.asyncio import Valkey
from pydantic import ValidationError
from dataclasses import dataclass, field

from . import schemas
from .settings import MastodonSettings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MastodonStreamer:
    """
    Streamer to get live data from Mastodon
    """

    settings: MastodonSettings = field(default_factory=MastodonSettings)
    status_events: set[schemas.EventType] = field(
        default_factory=partial(set, (schemas.EventType.update,))
    )

    @staticmethod
    def __wrap(doc: schemas.Status) -> dict:
        """
        Wrap document into a dictionary to be sent to the Valkey Queue for
        processing
        :param doc:
        :return:
        """
        return {"source": "mastodon", "data": doc.model_dump(mode="json")}

    async def statuses_from_event_stream(
        self,
        event_stream: AsyncIterator[str],
    ) -> AsyncIterator[schemas.Status | None]:
        """
        Receive events from stream and yield the statuses from "update"-type events (posts).
        :param event_stream: Stream yielding lines from the Mastodon Server feed
        :return:
        """
        expecting_data = False
        async for line in event_stream:
            if line.strip() == ":thump":
                logger.debug("Ping signal from server")
                yield None
                continue

            if expecting_data:
                if not line.startswith("data:"):
                    logger.error("Expected a data line but received none!")
                    expecting_data = False
                    continue

                try:
                    status = schemas.Status.model_validate_json(
                        line[5:].strip()
                    )
                    yield status
                except ValidationError as e:
                    logger.error(
                        "Invalid data received - unable to parse: %s", e
                    )

                expecting_data = False
                continue

            event_pat = re.search(r"^event:\s+(\w+(?:\.\w+)?)", line)
            if event_pat and event_pat.group(1) in self.status_events:
                logger.debug("Update event - expecting status data")
                expecting_data = True
            else:
                yield None

        logger.info("Streaming done")

    async def __stream_elements(
        self,
        path: str,
        headers: dict[str, str],
        params: dict[str, str | int | bool] | None = None,
    ) -> AsyncIterator[schemas.Status | None]:
        """
        Stream statuses from the Mastodon feed
        :param headers:
        :param params:
        :return:
        """
        url = f"{self.settings.base_url}/{path}"
        redirected = False
        async with httpx.AsyncClient(headers=headers, timeout=30) as client:
            # Check for redirection
            async with client.stream(
                "GET", url, headers=headers, params=params
            ) as stream:
                logger.info(
                    "Connection established (%s)[%d]", url, stream.status_code
                )
                # Some servers redirect to an alternate URL for streaming
                if stream.status_code // 100 == 3:
                    logger.info(
                        "Redirected to: %s", stream.headers.get("Location")
                    )
                    url = stream.headers.get("Location")
                    redirected = True

                else:
                    async for status in self.statuses_from_event_stream(
                        stream.aiter_lines()
                    ):
                        yield status

            if not redirected:
                return

            # In case redirected
            async with client.stream(
                "GET", url, timeout=60, params=params
            ) as stream:
                async for status in self.statuses_from_event_stream(
                    stream.aiter_lines()
                ):
                    yield status

    async def stream_public_timeline(
        self, max_elements: int | None = None, local: bool = False
    ) -> AsyncIterator[schemas.Status | None]:
        """
        Stream events from the public timeline of the Mastodon Server
        :return:
        """
        headers = {
            "User-Agent": self.settings.user_agent,
            "Authorization": f"Bearer {self.settings.auth_token}",
        }
        params = {}
        path = "api/v1/streaming/public"
        if local:
            path = f"{path}/local"
        i = 0
        async for item in self.__stream_elements(path, headers, params):
            if item:
                i += 1
            yield item

            if max_elements and i >= max_elements:
                logger.info("Reached limit (%d) stopping stream")
                break

        logger.info("Streamed %d total items from %s", i, path)

    async def stream_hashtag(
        self, hashtag: str, max_elements: int | None = None, local: bool = False
    ) -> AsyncIterator[schemas.Status | None]:
        """
        Stream statuses from the timeline of a given hashtag on the Mastodon server.
        :param hashtag:
        :param max_elements:
        :param local:
        :return:
        """
        headers = {
            "User-Agent": self.settings.user_agent,
            "Authorization": f"Bearer {self.settings.auth_token}",
        }
        params = {"local": local, "tag": hashtag.lstrip("#")}
        path = "api/v1/streaming/hashtag"
        i = 0
        async for item in self.__stream_elements(path, headers, params):
            if item:
                i += 1
            yield item

            if max_elements and i >= max_elements:
                logger.info("Reached limit (%d) stopping stream")
                break

        logger.info("Streamed %d total items from %s [%s]", i, path, hashtag)

    async def stream_to_vk(
        self,
        vk: Valkey,
        vk_list: str = "social-posts-index",
        max_time: float = 120.0,
        hashtag: str | None = None,
        local: bool = True,
    ) -> int:
        """
        Stream to Valkey List. Stop after the specified amount of time (seconds).
        :param vk:
        :param vk_list:
        :param max_time:
        :param hashtag:
        :param local:
        :return:
        """
        start = time.time()
        total = 0
        if hashtag:
            async for doc in self.stream_hashtag(hashtag, local=local):
                if doc:
                    await vk.lpush(
                        vk_list,
                        json.dumps(self.__wrap(doc)),
                    )
                    total += 1

                if (time.time() - start) > max_time:
                    break
        else:
            async for doc in self.stream_public_timeline(local=local):
                if doc:
                    await vk.lpush(
                        vk_list,
                        json.dumps(self.__wrap(doc)),
                    )
                    logger.info("Pushed element")
                    total += 1

                if (time.time() - start) > max_time:
                    break

        return total
