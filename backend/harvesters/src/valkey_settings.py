from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ValkeySettings(BaseSettings):
    """
    Settings to connect to valkey / redis for Keda orchestration and dispatch.
    """

    host: str = Field(default="localhost")
    port: int = Field(default=6379, gt=0)

    model_config = SettingsConfigDict(env_prefix="VALKEY_")
