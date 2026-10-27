import logging
from mastodon import Mastodon
from datetime import UTC, datetime
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

    def close(self) -> None:
        """Release the reusable HTTP session owned by this harvester."""
        self.client.session.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

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
        if start_date.tzinfo is None:
            start_date = start_date.replace(tzinfo=UTC)
        if end_date.tzinfo is None:
            end_date = end_date.replace(tzinfo=UTC)
        if start_date >= end_date:
            raise ValueError("start_date must be earlier than end_date")
        params = params or MastodonSearchParams()
        if params.limit is not None and params.limit <= 0:
            return
        if params.hashtag:
            method = self.client.timeline_hashtag
            search_params = {
                "hashtag": params.hashtag,
                "min_id": start_date,
                "max_id": end_date,
                "local": params.local,
                "limit": 40,
            }
        else:
            method = self.client.timeline
            search_params = {
                "timeline": params.timeline,
                "min_id": start_date,
                "max_id": end_date,
                "local": params.local,
                "limit": 40,
            }

        results = method(**search_params)
        total = 0
        previous_ids: set[str] = set()
        previous_oldest: int | None = None
        while results:
            # Timeline pages are ordered by descending creation IDs. Stop if a
            # buggy/repeated cursor fails to move backwards, without retaining
            # the entire history in memory.
            oldest = min(int(status.id) for status in results)
            if previous_oldest is not None and oldest >= previous_oldest:
                logger.warning("Mastodon pagination made no progress")
                return
            page_ids = set()
            for status in results:
                ident = str(status.id)
                if ident in previous_ids or ident in page_ids:
                    continue
                page_ids.add(ident)
                created = status.created_at
                if created.tzinfo is None:
                    created = created.replace(tzinfo=UTC)
                if created < start_date:
                    return
                if created > end_date:
                    continue
                yield status
                total += 1
                if params.limit is not None and total >= params.limit:
                    return
            previous_ids = page_ids
            previous_oldest = oldest
            results = self.client.fetch_next(results)
