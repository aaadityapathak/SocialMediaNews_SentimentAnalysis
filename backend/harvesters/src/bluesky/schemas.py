from datetime import datetime
from pydantic import BaseModel


class CommitRecord(BaseModel):
    text: str | None = None
    createdAt: datetime | None = None


class Commit(BaseModel):
    operation: str | None = None
    collection: str | None = None
    rkey: str | None = None
    record: CommitRecord | None = None
    cid: str | None = None


class Identity(BaseModel):
    handle: str | None = None


class JetStreamPost(BaseModel):
    did: str | None = None
    time_us: int | None = None
    kind: str | None = None
    identity: Identity | None = None
    commit: Commit | None = None

    @property
    def text(self) -> str | None:
        return (
            self.commit.record.text
            if self.commit and self.commit.record
            else None
        )

    @property
    def created_at(self) -> datetime | None:
        return (
            self.commit.record.createdAt
            if self.commit and self.commit.record
            else None
        )

    @property
    def handle(self) -> str | None:
        return self.identity.handle if self.identity else None

    @property
    def uri(self) -> str | None:
        if not self.did or not self.commit or not self.commit.rkey:
            return None
        return f"at://{self.did}/app.bsky.feed.post/{self.commit.rkey}"
