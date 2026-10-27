from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ThreadsStreamSettings(BaseSettings):
    """Settings for Threads scraper and Elasticsearch"""

    elastic_host: str = Field(
        default="https://localhost:9200", alias="ELASTIC_HOST"
    )
    elastic_api_key: str = Field(default="", alias="ELASTIC_API_KEY")
    es_index: str = Field(default="threads_posts", alias="ES_INDEX")
    max_workers: int = Field(default=3, ge=1, le=8)
    max_scrolls: int = Field(default=8, ge=0, le=100)
    keyword_timeout_seconds: float = Field(default=60, gt=0)
    harvest_timeout_seconds: float = Field(default=90, gt=0)
    fission_keyword_limit: int = Field(default=5, ge=1)

    # Expanded, specific Australian Keywords
    keywords: list[str] = [
        # Cities & States
        "Melbourne",
        "Sydney",
        "Brisbane",
        "Perth",
        "Adelaide",
        "Hobart",
        "Canberra",
        "Darwin",
        # Transport & Infrastructure
        "Qantas",
        "Jetstar",
        "Virgin Australia",
        "Myki",
        "Opal Card",
        "Translink",
        "Metro Trains",
        "NBN",
        # Politics & Economy
        "Albanese",
        "Dutton",
        "ATO",
        "Centrelink",
        "Medicare",
        "RBA",
        "Superannuation",
        "Negative Gearing",
        # Retail & Culture
        "Woolworths",
        "Coles",
        "Bunnings",
        "Kmart",
        "Telstra",
        "Optus",
        "AFL",
        "NRL",
        "Cricket Australia",
    ]

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
