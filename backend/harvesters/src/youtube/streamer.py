# Team 23 — COMP90024 — YouTube Streamer
import os
import json
import logging
from valkey import Valkey
from dataclasses import dataclass, field
from datetime import datetime

from .youtube import YoutubeHarvester
from .settings import YoutubeSettings
from .defaults import SEARCH_QUERIES

log = logging.getLogger(__name__)

VIDEOS_INDEX = "youtube-videos-idx"
COMMENTS_INDEX = "youtube-comments-idx"
REPLIES_INDEX = "youtube-replies-idx"


@dataclass(frozen=True)
class YoutubeStreamer:
    """
    Harvests YouTube data and indexes it across three ElasticSearch indices:
    videos, comments, and replies.
    """

    settings: YoutubeSettings = field(default_factory=YoutubeSettings)

    def harvest_to_vk(
        self,
        vk: Valkey,
        start: datetime,
        end: datetime,
        queries: dict = None,
    ) -> dict:
        """
        Run the YouTube harvester for the given time window and push all
        results into Valkey for processing. Returns counts per index.
        :param vk: Valkey client
        :param start: Start of the harvest window
        :param end: End of the harvest window
        :param queries: Topic → search queries dict; defaults to SEARCH_QUERIES
        :return: {"videos": int, "comments": int, "replies": int}
        """
        os.environ["YOUTUBE_API_KEY"] = self.settings.api_key
        harvester = YoutubeHarvester()
        counts = {"videos": 0, "comments": 0, "replies": 0}

        for video in harvester.run(
            start, end, queries=queries or SEARCH_QUERIES
        ):
            self._index_video(vk, video)
            counts["videos"] += 1

            if video.get("comments"):
                for comment in video["comments"]:
                    self._index_comment(vk, comment, video)
                    counts["comments"] += 1

                    if comment.get("replies"):
                        for reply in comment["replies"]:
                            self._index_reply(vk, reply, comment, video)
                            counts["replies"] += 1

        log.info(
            "YouTube harvest complete: %d videos, %d comments, %d replies",
            counts["videos"],
            counts["comments"],
            counts["replies"],
        )
        return counts

    def _index_video(self, vk: Valkey, video: dict) -> None:
        doc = {k: v for k, v in video.items() if k != "comments"}
        wrapped = {
            "source": "youtube",
            "data": {"kind": "video", "record": doc},
        }
        vk.lpush("social-posts-index", json.dumps(wrapped))

    def _index_comment(self, vk: Valkey, comment: dict, video: dict) -> None:
        doc = {
            "comment_id": comment["comment_id"],
            "video_id": video["video_id"],
            "video_topic": video["topic"],
            "video_channel": video["channel"],
            "video_published": video["published"],
            "text": comment.get("textOriginal", ""),
            "author": comment.get("authorDisplayName", ""),
            "like_count": comment.get("likeCount", 0),
            "published_at": comment.get("publishedAt"),
            "updated_at": comment.get("updatedAt"),
        }
        wrapped = {
            "source": "youtube",
            "data": {"kind": "comment", "record": doc},
        }
        vk.lpush("social-posts-index", json.dumps(wrapped))

    def _index_reply(
        self, vk: Valkey, reply: dict, comment: dict, video: dict
    ) -> None:
        doc = {
            "reply_id": reply["reply_id"],
            "comment_id": comment["comment_id"],
            "video_id": video["video_id"],
            "video_topic": video["topic"],
            "video_channel": video["channel"],
            "text": reply.get("textOriginal", ""),
            "author": reply.get("authorDisplayName", ""),
            "like_count": reply.get("likeCount", 0),
            "published_at": reply.get("publishedAt"),
            "updated_at": reply.get("updatedAt"),
        }
        wrapped = {
            "source": "youtube",
            "data": {"kind": "reply", "record": doc},
        }
        vk.lpush("social-posts-index", json.dumps(wrapped))
