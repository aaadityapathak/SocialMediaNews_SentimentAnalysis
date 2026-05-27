from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class YoutubeSettings(BaseSettings):
    api_key: str = Field(description="YouTube Data API v3 key")
    model_config = SettingsConfigDict(env_prefix="YOUTUBE_")
