import os
import logging
import datetime as dt

from dataclasses import dataclass, field
from typing import Optional, Iterator, Dict, List
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from base import BaseHarvester
from .defaults import (
    MAX_VIDEOS_PER_QUERY,
    MAX_COMMENTS_PER_VIDEO,
    MAX_REPLIES_PER_COMMENT,
    SEARCH_QUERIES,
)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger(__name__)


@dataclass(slots=True)
class YoutubeSearchParams:
    """
    Search parameters for the Youtube API.
    """

    max_videos: int = MAX_VIDEOS_PER_QUERY
    max_comments: int = MAX_COMMENTS_PER_VIDEO
    search_queries: Dict[str, List[str]] = field(
        default_factory=lambda: SEARCH_QUERIES
    )


class YoutubeHarvester(BaseHarvester[dict]):
    """
    Harvester for Youtube Data
    """

    def __init__(self):
        self._client = None

    def _connect(self) -> None:
        api_key = os.environ["YOUTUBE_API_KEY"]
        self._client = build("youtube", "v3", developerKey=api_key)
        log.info("Connected to YouTube API")

    def _get_videos(
        self, query: str, published_after: str, published_before: str
    ) -> list:
        videos = []
        try:
            response = (
                self._client.search()
                .list(
                    q=query,
                    part="snippet",
                    type="video",
                    relevanceLanguage="en",
                    regionCode="AU",
                    publishedAfter=published_after,
                    publishedBefore=published_before,
                    maxResults=MAX_VIDEOS_PER_QUERY,
                    order="relevance",
                )
                .execute()
            )

            for item in response.get("items", []):
                videos.append(
                    {
                        "video_id": item["id"]["videoId"],
                        "title": item["snippet"]["title"],
                        "channel": item["snippet"]["channelTitle"],
                        "channel_id": item["snippet"]["channelId"],
                        "description": item["snippet"]["description"],
                        "published": item["snippet"]["publishedAt"],
                        "query": query,
                    }
                )

            log.info(
                f"YouTube | Found {len(videos)} videos for query: '{query}'"
            )

            videos = self._filter_videos_without_comments(videos)

            log.info(
                f"YouTube | {len(videos)} videos with comments for query: '{query}'"
            )

        except HttpError as e:
            log.error(f"YouTube | _get_videos Search error for '{query}': {e}")

        return videos

    def _filter_videos_without_comments(self, videos: list) -> list:
        if not videos:
            return videos
        try:
            video_ids = [v["video_id"] for v in videos]
            response = (
                self._client.videos()
                .list(part="statistics", id=",".join(video_ids))
                .execute()
            )
            has_comments = {
                item["id"]
                for item in response.get("items", [])
                if int(item.get("statistics", {}).get("commentCount", 0)) > 0
            }
            log.info(
                f"YouTube | _filter_videos_without_comments {len(has_comments)} videos with comments"
            )
            return [v for v in videos if v["video_id"] in has_comments]
        except HttpError as e:
            log.error(f"YouTube | _filter_videos_without_comments error: {e}")
            return videos

    def _get_replies(self, comment_id: str) -> list:
        replies = []
        try:
            request = self._client.comments().list(
                part="snippet",
                parentId=comment_id,
                maxResults=MAX_REPLIES_PER_COMMENT,
                textFormat="plainText",
            )
            while request:
                response = request.execute()
                for item in response.get("items", []):
                    snippet = item["snippet"]
                    snippet["reply_id"] = item["id"]
                    replies.append(snippet)

                if (
                    "nextPageToken" in response
                    and len(replies) < MAX_REPLIES_PER_COMMENT
                ):
                    request = self._client.comments().list(
                        part="snippet",
                        parentId=comment_id,
                        maxResults=MAX_REPLIES_PER_COMMENT,
                        pageToken=response["nextPageToken"],
                        textFormat="plainText",
                    )
                else:
                    break

        except HttpError as e:
            log.error(
                f"YouTube | _get_replies error for comment {comment_id}: {e}"
            )

        return replies

    def _get_comments(
        self, video_id: str, published_after: Optional[str] = None
    ) -> list:
        comments = []
        try:
            request = self._client.commentThreads().list(
                part="snippet",
                videoId=video_id,
                maxResults=MAX_COMMENTS_PER_VIDEO,
                order="time",
                textFormat="plainText",
            )

            while request:
                response = request.execute()
                for item in response.get("items", []):
                    comment_id = item["snippet"]["topLevelComment"]["id"]
                    snippet = item["snippet"]["topLevelComment"]["snippet"]
                    snippet["comment_id"] = comment_id

                    if (
                        published_after
                        and snippet.get("publishedAt", "") < published_after
                    ):
                        continue

                    if item["snippet"]["totalReplyCount"] > 0:
                        snippet["replies"] = self._get_replies(comment_id)
                    else:
                        snippet["replies"] = []

                    comments.append(snippet)

                if (
                    "nextPageToken" in response
                    and len(comments) < MAX_COMMENTS_PER_VIDEO
                ):
                    request = self._client.commentThreads().list(
                        part="snippet",
                        videoId=video_id,
                        maxResults=MAX_COMMENTS_PER_VIDEO,
                        pageToken=response["nextPageToken"],
                        textFormat="plainText",
                    )
                else:
                    break

        except HttpError as e:
            log.error(f"YouTube | _get_comments error for {video_id}: {e}")

        return comments

    def _collect(
        self, start_date: str, end_date: str, queries: dict
    ) -> Iterator[dict]:
        all_data = []
        seen_ids = set()

        for topic, topic_queries in queries.items():
            for query in topic_queries:
                for video in self._get_videos(query, start_date, end_date):
                    if video["video_id"] in seen_ids:
                        continue
                    seen_ids.add(video["video_id"])
                    video["topic"] = topic
                    video["comments"] = self._get_comments(
                        video["video_id"], published_after=start_date
                    )
                    yield video

        log.info(
            f"YouTube | _collect | {start_date} and {end_date} | {len(all_data)} unique videos"
        )

    def run(
        self, start_date: dt.datetime, end_date: dt.datetime, **kwargs
    ) -> Iterator[dict]:
        queries = kwargs.get("queries", SEARCH_QUERIES)
        self._connect()
        yield from self._collect(
            start_date.isoformat(), end_date.isoformat(), queries
        )
