from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class GdeltStreamSettings(BaseSettings):
    """
    Settings for the live GDELT 2.0 polling daemon.
    """

    update_url: str = Field(
        default="http://data.gdeltproject.org/gdeltv2/lastupdate.txt",
        description="URL where GDELT publishes its latest 15m update timestamp",
    )
    poll_interval_seconds: int = Field(
        default=60,
        gt=0,
        description="How often to check for a new update (in seconds)",
    )
    raw_dir: str = Field(
        default="./database/gdelt/raw",
        description="Temporary directory for downloaded ZIPs before deletion",
    )
    target_adm1: str | None = Field(
        default="AS07",
        description="Target FIPS region code (e.g., AS07 for Victoria, Australia)",
    )
    es_index: str = "gdelt-index"
    model_config = SettingsConfigDict(
        env_prefix="GDELT_", env_file_encoding="utf-8", extra="ignore"
    )
