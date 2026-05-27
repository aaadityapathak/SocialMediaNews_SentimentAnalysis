import logging
from mastodon import Mastodon
from datetime import datetime
from dataclasses import dataclass
from typing import Iterator, Literal
from mastodon.return_types import Status

from base import BaseHarvester
from .settings import MastodonSettings

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class MastodonSearchParams:
    """
    Search parameters for the Mastodon API.
    """

    hashtag: str | None = None
    timeline: Literal["public", "home"] = "public"
    local: bool = True
    limit: int | None = None


class MastodonHarvester(BaseHarvester[Status]):
    """
    Harvester to gather Mastodon posts
    """

    def __init__(self, settings: MastodonSettings | None = None):
        self.__settings = settings or MastodonSettings()

        if not self.settings.auth_token:
            raise AttributeError(
                "You must provide a Mastodon token for gathering data!"
            )

        self.__client = Mastodon(
            api_base_url=self.settings.base_url,
            access_token=self.settings.auth_token,
            user_agent=self.settings.user_agent,
        )

    @property
    def settings(self) -> MastodonSettings:
        """
        Return the Mastodon settings for the harvester.
        """
        return self.__settings

    @property
    def client(self) -> Mastodon:
        """
        Return the client for Mastodon.
        """
        return self.__client

    def run(
        self,
        start_date: datetime,
        end_date: datetime,
        params: MastodonSearchParams | None = None,
        **kwargs,
    ) -> Iterator[Status]:
        """
        Run Mastodon harvesting.
        :param start_date:
        :param end_date:
        :param params: Parameters to configure Mastodon Search
        :param kwargs:
        :return:
        """
        params = params or MastodonSearchParams()
        if params.hashtag:
            method = self.client.timeline_hashtag
            search_params = {
                "hashtag": params.hashtag,
                "min_id": start_date,
                "max_id": end_date,
                "local": params.local,
            }
        else:
            method = self.client.timeline
            search_params = {
                "timeline": params.timeline,
                "min_id": start_date,
                "max_id": end_date,
                "local": params.local,
            }

        results = method(**search_params)
        total = 0
        while results is not None and len(results) > 0:
            for status in results:
                total += 1
                if params.limit and total > params.limit:
                    logger.warning(
                        "Reached maximum number of posts (%d)!", params.limit
                    )
                    return

                # Sanity check since timestamp checks on Mastodon are only approximate
                effective_time = status.edited_at or status.created_at
                if effective_time < start_date:
                    logger.info(
                        "Reached status out-of-bounds (%s < %s) Stopping.",
                        effective_time.isoformat(),
                        start_date.isoformat(),
                    )
                    return

                yield status

            results = self.client.fetch_next(results)
