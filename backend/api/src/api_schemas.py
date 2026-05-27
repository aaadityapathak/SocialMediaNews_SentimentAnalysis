from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class TrendsRequest(BaseModel):
    """
    Request to get a weekly aggregate timeseries of emotions corresponding
    to a given topic from the social posts index
    """

    topic_name: str
    start_date: datetime | None = None
    aggregate_by: Literal["week", "day", "month"] = "week"
    keywords: list[str] = Field(default_factory=list)
    exclude_neutral: bool = False
