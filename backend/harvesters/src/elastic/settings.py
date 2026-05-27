from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ESSettings(BaseSettings):
    """
    Settings for connecting to ElasticSearch
    """

    host: str = Field(
        default="https://localhost:9200", description="ElasticSearch Host"
    )
    api_key: str = Field(description="ElasticSearch API key")

    model_config = SettingsConfigDict(env_prefix="ELASTIC_")
