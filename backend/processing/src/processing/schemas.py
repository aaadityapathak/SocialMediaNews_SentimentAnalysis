from pydantic import BaseModel, TypeAdapter
from typing import Literal, Any, TypedDict, NotRequired


class MastodonRecord(BaseModel):
    """
    Record of a post received from Mastodon
    """

    source: Literal["mastodon"] = "mastodon"
    data: dict[str, Any]
    save_common_idx: bool = True
    save_provider_idx: bool = True


class BlueskyRecord(BaseModel):
    """
    Record of a post received from Bluesky.
    """

    source: Literal["bluesky"] = "bluesky"
    data: dict[str, Any]
    save_common_idx: bool = True
    save_provider_idx: bool = True


class YTItem(BaseModel):
    """
    Youtube item. Can be a video, comment, or reply
    """

    kind: Literal["video", "comment", "reply"]
    record: dict[str, Any]
    save_common_idx: bool = True
    save_provider_idx: bool = True


class YouTubeRecord(BaseModel):
    """
    Record for a comment / reply from youtube
    """

    source: Literal["youtube"] = "youtube"
    data: YTItem
    save_common_idx: bool = True
    save_provider_idx: bool = True


SocialMediaRecord = MastodonRecord | BlueskyRecord | YouTubeRecord
RecordAdapter = TypeAdapter(MastodonRecord | BlueskyRecord | YouTubeRecord)


class Sentiment(TypedDict):
    """
    Sentiment analysis result.
    """

    positive: float
    neutral: float
    negative: float
    sentiment: str  # dominant label (argmax)


class Emotion(TypedDict):
    """
    Emotion analysis entry.
    """

    label: str
    score: float


class CommonRecord(TypedDict):
    """
    Record to insert into common data index.
    """

    platform: str
    record_type: str
    platform_post_id: str
    common_id: str
    text: str
    account: NotRequired[str | None]
    created_at: str | None
    ingested_at: str
    source_url: NotRequired[str | None]
    source_meta: NotRequired[dict]
    sentiment: NotRequired[Sentiment]
    emotion: NotRequired[list[Emotion]]
