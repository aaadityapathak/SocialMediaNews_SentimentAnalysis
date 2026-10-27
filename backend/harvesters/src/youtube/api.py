"""Small, bounded helpers for the YouTube Data API."""

import json
from datetime import UTC, datetime

from googleapiclient.errors import HttpError


def utc_datetime(value: str | datetime) -> datetime:
    """Interpret legacy naive dates as UTC and normalize aware dates."""
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def iter_items(resource, *, limit, page_size, num_retries=3, **params):
    """Yield at most ``limit`` items without following repeated page tokens."""
    remaining = limit
    token = None
    seen_tokens = set()
    while remaining > 0:
        page_params = {**params, "maxResults": min(page_size, remaining)}
        if token:
            page_params["pageToken"] = token
        response = resource.list(**page_params).execute(num_retries=num_retries)
        items = response.get("items", [])
        for item in items[:remaining]:
            remaining -= 1
            yield item
        token = response.get("nextPageToken")
        if not items or not token or token in seen_tokens:
            return
        seen_tokens.add(token)


def unavailable_comments(error: HttpError) -> bool:
    """Only suppress expected resource removal/disabled-comment errors."""
    try:
        details = json.loads(error.content).get("error", {}).get("errors", [])
    except (ValueError, TypeError, AttributeError):
        return False
    reasons = {item.get("reason") for item in details}
    return bool(reasons) and reasons <= {
        "commentsDisabled",
        "commentNotFound",
        "videoNotFound",
    }
