from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from .defaults import (
    MAX_COMMENTS_PER_VIDEO,
    MAX_REPLIES_PER_COMMENT,
    MAX_VIDEOS_PER_QUERY,
)


class YoutubeSettings(BaseSettings):
    api_key: str = Field(description="YouTube Data API v3 key")
    max_videos: int = Field(default=MAX_VIDEOS_PER_QUERY, ge=0)
    max_comments: int = Field(default=MAX_COMMENTS_PER_VIDEO, ge=0)
    max_replies: int = Field(default=MAX_REPLIES_PER_COMMENT, ge=0)
    max_retries: int = Field(default=3, ge=0, le=10)
    queue_batch_size: int = Field(default=100, ge=1, le=1000)
    model_config = SettingsConfigDict(env_prefix="YOUTUBE_")
