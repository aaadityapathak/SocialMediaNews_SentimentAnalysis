from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class MastodonSettings(BaseSettings):
    """
    Settings for Mastodon client
    """

    api_name: str = Field(
        description="Name for the Mastodon application",
        default="uom-comp90024-dstilesrosse-1",
    )
    base_url: str = Field(
        description="Base URL of Mastodon API to use",
        default="https://mastodon.au",
    )
    auth_token: str | None = Field(
        description="Auth token for Mastodon API", default=None, repr=False
    )
    user_agent: str = Field(
        description="User Agent to use for Mastodon requests",
        default="unimelb-c90024-t23",
    )

    output_path: Path = Field(
        default=Path(__file__).parents[1] / "mastodon.secret",
        description="Path to store the Mastodon credential",
    )

    model_config = SettingsConfigDict(env_prefix="MASTODON_")
