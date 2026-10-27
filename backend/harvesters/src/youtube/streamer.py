"""Publish normalized YouTube records using bounded Valkey batches."""

import json
import logging
from contextlib import closing
from dataclasses import dataclass, field
from datetime import datetime

from valkey import Valkey

from .records import (
    comment_record,
    iter_records,
    reply_record,
    video_record,
    wrap_record,
)
from .settings import YoutubeSettings
from .youtube import YoutubeHarvester, YoutubeSearchParams

log = logging.getLogger(__name__)

VIDEOS_INDEX = "youtube-videos-idx"
COMMENTS_INDEX = "youtube-comments-idx"
REPLIES_INDEX = "youtube-replies-idx"
QUEUE_NAME = "social-posts-index"


@dataclass(frozen=True)
class YoutubeStreamer:
    """Harvest and enqueue videos, comments, and replies for processing."""

    settings: YoutubeSettings = field(default_factory=YoutubeSettings)

    def harvest_to_vk(
        self,
        vk: Valkey,
        start: datetime,
        end: datetime,
        queries: dict | None = None,
    ) -> dict:
        params = YoutubeSearchParams(
            max_videos=self.settings.max_videos,
            max_comments=self.settings.max_comments,
            max_replies=self.settings.max_replies,
        )
        harvester = YoutubeHarvester(
            api_key=self.settings.api_key,
            search_params=params,
            num_retries=self.settings.max_retries,
        )
        counts = {"videos": 0, "comments": 0, "replies": 0}
        count_keys = {
            "video": "videos",
            "comment": "comments",
            "reply": "replies",
        }
        harvest_queries = params.search_queries if queries is None else queries
        # Explicitly close the generator if publishing raises midway through it.
        with closing(
            harvester.run(start, end, queries=harvest_queries)
        ) as videos:
            for video in videos:
                messages = []
                kinds = []
                for kind, record in iter_records(video):
                    messages.append(json.dumps(wrap_record(kind, record)))
                    kinds.append(kind)
                    if len(messages) >= self.settings.queue_batch_size:
                        vk.lpush(QUEUE_NAME, *messages)
                        for queued_kind in kinds:
                            counts[count_keys[queued_kind]] += 1
                        messages.clear()
                        kinds.clear()
                if messages:
                    vk.lpush(QUEUE_NAME, *messages)
                    for queued_kind in kinds:
                        counts[count_keys[queued_kind]] += 1
        log.info("YouTube harvest complete: %s", counts)
        return counts

    def _index_video(self, vk: Valkey, video: dict) -> None:
        vk.lpush(
            QUEUE_NAME, json.dumps(wrap_record("video", video_record(video)))
        )

    def _index_comment(self, vk: Valkey, comment: dict, video: dict) -> None:
        vk.lpush(
            QUEUE_NAME,
            json.dumps(wrap_record("comment", comment_record(comment, video))),
        )

    def _index_reply(
        self, vk: Valkey, reply: dict, comment: dict, video: dict
    ) -> None:
        vk.lpush(
            QUEUE_NAME,
            json.dumps(
                wrap_record("reply", reply_record(reply, comment, video))
            ),
        )
