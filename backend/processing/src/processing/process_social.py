import time
import logging
from typing import Any
from valkey import Valkey
from elasticsearch import Elasticsearch

from .indexer import Indexer
from .base import BaseProcessor
from .ml_client import MLServerClient
from .schemas import YTItem, CommonRecord

logger = logging.getLogger(__name__)


class MastodonProcessor(BaseProcessor):
    """
    Processor for Mastodon records
    """

    INDEX = "mastodon-idx"

    @property
    def provider(self) -> str:
        return "mastodon"

    def get_index(self, doc: Any) -> str:
        return self.INDEX

    def get_record_id(self, doc: Any) -> str:
        return doc["uri"]

    def process_record(self, doc: Any) -> dict:
        return doc

    def to_common_schema(self, doc: Any) -> CommonRecord:
        platform_post_id = doc["uri"]
        source_meta = {
            "visibility": doc.get("visibility"),
            "sensitive": doc.get("sensitive"),
            "tag_names": [
                t.get("name") for t in doc.get("tags", []) if t.get("name")
            ],
        }
        return {
            "platform": self.provider,
            "record_type": "post",
            "account": doc.get("account", {}).get("acct"),
            "platform_post_id": platform_post_id,
            "common_id": self.build_common_id(platform_post_id),
            "text": self._clean_text(doc.get("content")),
            "created_at": doc.get("created_at"),
            "ingested_at": self._now_iso(),
            "source_url": doc.get("url"),
            "source_meta": source_meta,
        }


class BlueskyProcessor(BaseProcessor):
    """
    Processor for Bluesky Records
    """

    INDEX = "bluesky-idx"

    @property
    def provider(self) -> str:
        return "bluesky"

    def get_index(self, doc: Any) -> str:
        return self.INDEX

    def get_record_id(self, doc: Any) -> str:
        did = doc.get("did")
        commit = doc.get("commit") or {}
        rkey = commit.get("rkey") or round(time.time())
        return doc.get("uri") or f"{did}:{rkey}"

    def process_record(self, doc: Any) -> dict:
        return doc

    def to_common_schema(self, doc: Any) -> CommonRecord:
        platform_post_id = self.get_record_id(doc)
        commit = doc.get("commit") or {}
        commit_record = commit.get("record") or {}
        identity = doc.get("identity") or {}
        source_meta = {
            "author_handle": identity.get("handle"),
            "matched_strong_keywords": doc.get("matched_strong_keywords", []),
            "matched_medium_keywords": doc.get("matched_medium_keywords", []),
            "matched_weak_keywords": doc.get("matched_weak_keywords", []),
            "matched_topic_keywords": doc.get("matched_topic_keywords", []),
        }
        return {
            "platform": self.provider,
            "record_type": "post",
            "account": identity.get("handle"),
            "platform_post_id": platform_post_id,
            "common_id": self.build_common_id(platform_post_id),
            "text": self._clean_text(commit_record.get("text")),
            "created_at": commit_record.get("createdAt"),
            "ingested_at": self._now_iso(),
            "source_url": doc.get("uri"),
            "source_meta": source_meta,
        }


class YouTubeProcessor(BaseProcessor):
    """
    Processor for youtube records
    """

    VIDEOS_INDEX = "youtube-videos-idx"
    COMMENTS_INDEX = "youtube-comments-idx"
    REPLIES_INDEX = "youtube-replies-idx"

    @property
    def provider(self) -> str:
        return "youtube"

    def get_index(self, doc: YTItem) -> str:
        """
        Get appropriate index for the element type
        :param doc:
        :return:
        """
        match doc.kind:
            case "video":
                return self.VIDEOS_INDEX
            case "comment":
                return self.COMMENTS_INDEX
            case "reply":
                return self.REPLIES_INDEX
            case _:
                raise ValueError(f"Unsupported YouTube kind: {doc.kind}")

    def get_record_id(self, doc: YTItem) -> str:
        match doc.kind:
            case "video":
                return str(doc.record["video_id"])
            case "comment":
                return str(doc.record["comment_id"])
            case "reply":
                return str(doc.record["reply_id"])
            case _:
                raise ValueError(f"Unsupported YouTube kind: {doc.kind}")

    def process_record(self, doc: YTItem) -> dict:
        return doc.record

    def to_common_schema(self, doc: YTItem) -> CommonRecord:
        platform_post_id = self.get_record_id(doc)
        source_meta = {"youtube_kind": doc.kind}
        return {
            "platform": self.provider,
            "record_type": doc.kind,
            "platform_post_id": platform_post_id,
            "account": doc.record.get("author"),
            "common_id": self.build_common_id(platform_post_id),
            "text": self._extract_youtube_text(doc.kind, doc.record),
            "created_at": self._extract_youtube_created_at(doc.record),
            "ingested_at": self._now_iso(),
            "source_url": self._extract_youtube_url(doc.kind, doc.record),
            "source_meta": source_meta,
        }

    @staticmethod
    def _extract_youtube_text(kind: str, doc: dict) -> str:
        if kind == "video":
            parts = [doc.get("title"), doc.get("description")]
            return BaseProcessor._clean_text(" ".join(p for p in parts if p))

        for key in ("text", "textOriginal", "textDisplay", "content"):
            if doc.get(key):
                return BaseProcessor._clean_text(doc.get(key))

        return ""

    @staticmethod
    def _extract_youtube_created_at(doc: dict):
        for key in ("published_at", "publishedAt", "created_at", "createdAt"):
            if doc.get(key):
                return doc.get(key)

        snippet = doc.get("snippet") or {}
        return snippet.get("publishedAt")

    @staticmethod
    def _extract_youtube_url(kind: str, doc: dict):
        for key in ("url", "source_url", "video_url"):
            if doc.get(key):
                return doc.get(key)

        if kind == "video" and doc.get("video_id"):
            return f"https://www.youtube.com/watch?v={doc['video_id']}"

        return None


def build_indexer(es: Elasticsearch, vk: Valkey, ml: MLServerClient) -> Indexer:
    return Indexer(
        es=es,
        vk=vk,
        processors={
            "mastodon": MastodonProcessor(ml),
            "bluesky": BlueskyProcessor(ml),
            "youtube": YouTubeProcessor(ml),
        },
    )
