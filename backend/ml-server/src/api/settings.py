from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class ServerSettings(BaseSettings):
    """
    Settings for the FastAPI inference server run
    """

    port: int = 8004
    host: str = "0.0.0.0"
    api_key: str = "key"

    model_config = SettingsConfigDict(env_prefix="SERVER_")


@lru_cache(maxsize=1)
def get_server_settings() -> ServerSettings:
    return ServerSettings()
