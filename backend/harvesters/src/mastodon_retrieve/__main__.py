"""
Mastodon retrieval test. Run this to fetch records from Mastodon. Run this script to fetch some records. Development Only.

"""

import fire
import logging
from pathlib import Path
from typing import TypeVar
from datetime import datetime, UTC, timedelta

from base import setup_logging
from .mastodon_harvest import MastodonHarvester, MastodonSearchParams

T = TypeVar("T")

setup_logging(logging.DEBUG)
logger = logging.getLogger(__name__)

out_path = Path(__file__).parents[2] / "mastodon-data.jsonl"
defaults = (datetime.now(UTC) - timedelta(days=30), datetime.now(UTC))


def gather_mastodon_records(
    start_time: datetime = defaults[0],
    end_time: datetime = defaults[1],
    hashtags: str | None = None,
    include_remote: bool = False,
    save_to: str | Path = out_path,
):
    """
    Gather Mastodon records with the given hashtag and save them.
    :param start_time:
    :param end_time:
    :param hashtags: Hashtags to search for (semicolon-separated)
    :param include_remote:
    :param save_to: Where to save the output file
    :return:
    """
    if hashtags:
        hashtags = hashtags.split(";")
    else:
        hashtags = [None]
    seen = set()

    with (
        MastodonHarvester() as harvester,
        open(save_to, "a", encoding="utf-8") as f,
    ):
        for hashtag in hashtags:
            params = MastodonSearchParams(
                hashtag=hashtag, local=not include_remote, timeline="public"
            )
            for stat in harvester.run(start_time, end_time, params=params):
                if stat.id in seen or stat.account.bot:
                    continue

                seen.add(stat.id)
                f.write(f"{stat.to_json(pretty=False)}\n")


if __name__ == "__main__":
    fire.Fire({"gather": gather_mastodon_records})
