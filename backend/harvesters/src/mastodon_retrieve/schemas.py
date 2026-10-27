from enum import StrEnum
from typing import Literal
from datetime import datetime
from markdownify import markdownify
from pydantic import BaseModel, Field, TypeAdapter, field_validator


class EventType(StrEnum):
    """
    Stream event types on Mastodon
    """

    delete = "delete"
    status = "status"
    update = "update"
    status_update = "status.update"


class Account(BaseModel):
    """
    Mastodon Account information received from Mastodon API
    """

    id: str
    username: str
    acct: str
    locked: bool
    bot: bool
    created_at: datetime


class HashTag(BaseModel):
    """
    A hashtag on a Mastodon post
    """

    name: str
    url: str


class Application(BaseModel):
    """
    An application used for posting to Mastodon
    """

    name: str
    website: str


class Status(BaseModel):
    """
    Status (Mastodon equivalent of a post) received from Mastodon API.
    """

    # Post metadata
    id: str
    visibility: Literal["public", "unlisted", "private", "direct"]
    uri: str
    url: str | None = None
    account: Account
    # application: Application | None = Field(default=None)
    created_at: datetime
    edited_at: datetime | None = Field(default=None)
    in_reply_to_id: str | None = None

    # Engagement
    replies_count: int | None = None
    reblogs_count: int | None = None
    favourites_count: int | None = None
    quotes_count: int | None = None

    # Post Content data
    sensitive: bool
    spoiler_text: str | None = Field(default=None)
    tags: list[HashTag] = Field(default_factory=list)
    content: str

    @field_validator("content", mode="after")
    @classmethod
    def html_to_markdown(cls, v: str) -> str:
        """
        Convert HTML content to markdown. This makes it less verbose and easier to process
        """
        return markdownify(v)


StatusesAdapter = TypeAdapter(list[Status])
