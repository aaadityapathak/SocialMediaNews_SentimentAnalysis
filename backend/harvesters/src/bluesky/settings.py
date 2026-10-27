from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class BlueskySettings(BaseSettings):
    """
    Settings for Bluesky streaming.
    """

    handle: str | None = Field(
        default=None,
        repr=False,
        description="Bluesky handle, e.g. USERNAME.bsky.social",
    )
    app_password: str | None = Field(
        default=None,
        repr=False,
        description="Bluesky app password",
    )
    jetstream_url: str = Field(
        default=(
            "wss://jetstream2.us-east.bsky.network/"
            "subscribe?wantedCollections=app.bsky.feed.post"
        ),
        description="JetStream websocket URL for Bluesky post events",
    )
    user_agent: str = Field(
        default="unimelb-comp90024-t23",
        description="User agent for Bluesky requests",
    )
    max_posts: int = Field(
        default=3000,
        gt=0,
        description="Maximum posts to stream before stopping",
    )
    max_retries: int = Field(default=3, ge=0)
    retry_backoff_seconds: float = Field(default=1.0, gt=0)
    output_path: Path = Field(
        default=Path(__file__).parents[2] / "bluesky-data.jsonl",
        description="Path to save streamed Bluesky records",
    )

    model_config = SettingsConfigDict(env_prefix="BLUESKY_")
