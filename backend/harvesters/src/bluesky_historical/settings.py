"""Historical search policy and validated collector settings."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_AU_SEARCH_QUERIES = [
    "auspol",
    "ausvotes",
    "australian government",
    "australia voting",
    "australian elections",
    "australia politics",
    "australian federal election",
    "election day australia",
    "labor party australia",
    "liberal party australia",
    "australian greens",
    "the nationals australia",
    "one nation australia",
    "teal independent",
    "anthony albanese",
    "peter dutton",
    "adam bandt",
    "jim chalmers",
    "sussan ley",
    "cost of living australia",
    "housing australia",
]

STRONG_AU_KEYWORDS = [
    "australia",
    "australian",
    "aussie",
    "aussies",
    "auspol",
    "ausvotes",
    "ausvotes25",
    "ausvotes2025",
    "new south wales",
    "queensland",
    "south australia",
    "western australia",
    "tasmania",
    "northern territory",
    "abc australia",
    "sbs australia",
    "guardian australia",
    "the australian",
    "straya",
    "labor party",
    "labour party",
    "liberal party",
    "australian greens",
    "the nationals",
    "federal election",
    "australian federal election",
    "election day",
    "polling booth",
    "preferential voting",
    "senate australia",
]

MEDIUM_AU_KEYWORDS = [
    "victoria state",
    "state of victoria",
    "victorian government",
    "victorian parliament",
    "nsw government",
    "nsw parliament",
    "qld government",
    "queensland government",
    "nswpol",
    "vicpol",
    "qldpol",
    "melbourne vic",
    "melbourne victoria",
    "sydney nsw",
    "brisbane qld",
    "canberra act",
    "adelaide sa",
    "perth wa",
    "hobart tas",
    "darwin nt",
    "gold coast qld",
    "gold coast queensland",
    "geelong vic",
    "geelong victoria",
    "cairns queensland",
    "wollongong nsw",
    "teals",
    "teal independent",
    "pauline hanson",
    "peter dutton",
    "adam bandt",
    "penny wong",
    "jim chalmers",
    "tanya plibersek",
    "sussan ley",
    "david littleproud",
    "jacqui lambie",
    "andrew wilkie",
    "david pocock",
    "cost of living",
    "housing crisis",
    "abc news",
    "sky news australia",
    "news.com.au",
    "marginal seat",
    "two party preferred",
    "primary vote",
]

WEAK_CITY_KEYWORDS = [
    "victoria",
    "melbourne",
    "sydney",
    "canberra",
    "adelaide",
    "brisbane",
    "perth",
    "hobart",
    "darwin",
    "geelong",
    "gold coast",
    "sunshine coast",
    "newcastle",
    "wollongong",
    "ballarat",
    "bendigo",
    "toowoomba",
    "townsville",
    "cairns",
    "launceston",
    "alp",
    "nlp",
    "one nation",
    "greens",
    "senate",
    "parliament",
    "electorate",
    "albo",
    "dutton",
    "bandt",
]


class BlueskyHistoricalSettings(BaseSettings):
    base_url: str = Field(default="https://bsky.social")
    create_session_endpoint: str = Field(
        default="/xrpc/com.atproto.server.createSession"
    )
    search_endpoint: str = Field(default="/xrpc/app.bsky.feed.searchPosts")

    handle: str = Field(description="Bluesky handle / identifier")
    app_password: str = Field(description="Bluesky app password", repr=False)

    user_agent: str = Field(default="unimelb-comp90024-t23-historical")
    timeout_seconds: float = Field(default=30.0, gt=0)

    index_name: str = Field(default="bluesky-historical-idx")
    page_size: int = Field(default=100, ge=1, le=100)
    max_pages: int = Field(default=5, ge=1)

    # Melbourne 2026-05-10 00:00 = UTC 2026-05-09T14:00:00Z
    cutoff_before: str = Field(default="2026-05-09T14:00:00Z")
    split_by_3day: bool = Field(default=True)

    model_config = SettingsConfigDict(
        env_prefix="BLUESKY_", validate_assignment=True
    )

    max_retries: int = Field(default=3, ge=0)
    retry_backoff_seconds: float = Field(default=2.0, gt=0)
    continue_on_error: bool = Field(default=True)
    checkpoint_path: str = Field(default="bluesky_historical_checkpoint.json")
    batch_size: int = Field(default=100, ge=1, le=1000)
    queue_limit: int = Field(default=12_000, gt=0)
    queue_wait_seconds: float = Field(default=60.0, gt=0)
    recent_ids_limit: int = Field(default=10_000, gt=0)
