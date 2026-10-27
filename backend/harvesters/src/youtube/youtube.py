"""Quota-conscious harvesting of videos, comments, and replies."""

import datetime as dt
import logging
import os
from collections.abc import Iterator
from dataclasses import dataclass, field

from base import BaseHarvester
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from .api import iter_items, unavailable_comments, utc_datetime
from .defaults import (
    MAX_COMMENTS_PER_VIDEO,
    MAX_REPLIES_PER_COMMENT,
    MAX_VIDEOS_PER_QUERY,
    SEARCH_QUERIES,
)

log = logging.getLogger(__name__)


@dataclass(slots=True)
class YoutubeSearchParams:
    """Per-query/video limits, independent of the API's page-size limits."""

    max_videos: int = MAX_VIDEOS_PER_QUERY
    max_comments: int = MAX_COMMENTS_PER_VIDEO
    search_queries: dict[str, list[str]] = field(
        default_factory=lambda: {
            key: list(value) for key, value in SEARCH_QUERIES.items()
        }
    )
    max_replies: int = MAX_REPLIES_PER_COMMENT

    def __post_init__(self):
        for name in ("max_videos", "max_comments", "max_replies"):
            value = getattr(self, name)
            if not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")


class YoutubeHarvester(BaseHarvester[dict]):
    """Yield unique videos with bounded comment and reply collections."""

    def __init__(
        self, api_key=None, search_params=None, client=None, num_retries=3
    ):
        if num_retries < 0:
            raise ValueError("num_retries must be non-negative")
        self._api_key = api_key
        self.params = search_params or YoutubeSearchParams()
        self._client = client
        self._owns_client = client is None
        self._num_retries = num_retries
        self._comment_availability = {}

    def _connect(self) -> None:
        api_key = self._api_key or os.environ["YOUTUBE_API_KEY"]
        self._client = build(
            "youtube", "v3", developerKey=api_key, cache_discovery=False
        )
        log.info("Connected to YouTube API")

    def close(self) -> None:
        if self._owns_client and self._client is not None:
            try:
                self._client.close()
            finally:
                self._client = None

    def _get_videos(
        self, query: str, published_after: str, published_before: str
    ) -> list:
        videos = []
        seen_ids = set()
        for item in iter_items(
            self._client.search(),
            limit=self.params.max_videos,
            page_size=50,
            num_retries=self._num_retries,
            q=query,
            part="snippet",
            type="video",
            relevanceLanguage="en",
            regionCode="AU",
            publishedAfter=published_after,
            publishedBefore=published_before,
            order="relevance",
        ):
            video_id = item["id"]["videoId"]
            if video_id in seen_ids:
                continue
            seen_ids.add(video_id)
            snippet = item["snippet"]
            videos.append(
                {
                    "video_id": video_id,
                    "title": snippet["title"],
                    "channel": snippet["channelTitle"],
                    "channel_id": snippet["channelId"],
                    "description": snippet.get("description", ""),
                    "published": snippet["publishedAt"],
                    "query": query,
                }
            )
        return self._filter_videos_without_comments(videos)

    def _filter_videos_without_comments(self, videos: list) -> list:
        # A video can match many queries; fetch its statistics only once per run.
        missing = list(
            dict.fromkeys(
                video["video_id"]
                for video in videos
                if video["video_id"] not in self._comment_availability
            )
        )
        for offset in range(0, len(missing), 50):
            batch = missing[offset : offset + 50]
            response = (
                self._client.videos()
                .list(part="statistics", id=",".join(batch))
                .execute(num_retries=self._num_retries)
            )
            available = {
                item["id"]
                for item in response.get("items", [])
                if int(item.get("statistics", {}).get("commentCount", 0)) > 0
            }
            self._comment_availability.update(
                {key: key in available for key in batch}
            )
        return [v for v in videos if self._comment_availability[v["video_id"]]]

    def _get_replies(self, comment_id: str) -> list:
        replies = []
        seen_ids = set()
        try:
            for item in iter_items(
                self._client.comments(),
                limit=self.params.max_replies,
                page_size=100,
                num_retries=self._num_retries,
                part="snippet",
                parentId=comment_id,
                textFormat="plainText",
            ):
                if item["id"] not in seen_ids:
                    seen_ids.add(item["id"])
                    replies.append({**item["snippet"], "reply_id": item["id"]})
        except HttpError as error:
            if not unavailable_comments(error):
                raise
            log.info("Replies unavailable for comment %s", comment_id)
        return replies

    def _get_comments(
        self, video_id: str, published_after: str | None = None
    ) -> list:
        comments = []
        seen_ids = set()
        cutoff = utc_datetime(published_after) if published_after else None
        try:
            for item in iter_items(
                self._client.commentThreads(),
                limit=self.params.max_comments,
                page_size=100,
                num_retries=self._num_retries,
                part="snippet,replies",
                videoId=video_id,
                order="time",
                textFormat="plainText",
            ):
                top = item["snippet"]["topLevelComment"]
                comment_id = top["id"]
                snippet = {**top["snippet"], "comment_id": comment_id}
                # Every page is ordered newest first: no older pages are needed.
                if cutoff and utc_datetime(snippet["publishedAt"]) < cutoff:
                    break
                if comment_id in seen_ids:
                    continue
                seen_ids.add(comment_id)
                total = item["snippet"].get("totalReplyCount", 0)
                embedded = list(
                    {
                        reply["id"]: reply
                        for reply in item.get("replies", {}).get("comments", [])
                    }.values()
                )
                needed = min(total, self.params.max_replies)
                if len(embedded) >= needed:
                    snippet["replies"] = [
                        {**reply["snippet"], "reply_id": reply["id"]}
                        for reply in embedded[:needed]
                    ]
                else:
                    snippet["replies"] = self._get_replies(comment_id)
                comments.append(snippet)
        except HttpError as error:
            if not unavailable_comments(error):
                raise
            log.info("Comments unavailable for video %s", video_id)
        return comments

    def _collect(
        self, start_date: str, end_date: str, queries: dict
    ) -> Iterator[dict]:
        seen_ids = set()
        seen_queries = set()
        for topic, topic_queries in queries.items():
            for query in topic_queries:
                if query in seen_queries:
                    continue
                seen_queries.add(query)
                for video in self._get_videos(query, start_date, end_date):
                    if video["video_id"] in seen_ids:
                        continue
                    seen_ids.add(video["video_id"])
                    video["topic"] = topic
                    video["comments"] = self._get_comments(
                        video["video_id"], published_after=start_date
                    )
                    yield video
        log.info("YouTube collected %d unique videos", len(seen_ids))

    def run(
        self, start_date: dt.datetime, end_date: dt.datetime, **kwargs
    ) -> Iterator[dict]:
        start, end = utc_datetime(start_date), utc_datetime(end_date)
        if start >= end:
            raise ValueError("start_date must be earlier than end_date")
        queries = kwargs.get("queries", self.params.search_queries)
        if not queries or self.params.max_videos == 0:
            return
        self._comment_availability.clear()
        try:
            if self._client is None:
                self._connect()
            yield from self._collect(
                start.isoformat(), end.isoformat(), queries
            )
        finally:
            self.close()
