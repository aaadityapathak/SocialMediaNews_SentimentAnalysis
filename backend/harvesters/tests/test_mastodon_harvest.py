import pytest
import asyncio
from datetime import datetime, UTC

from mastodon_retrieve import schemas
from mastodon_retrieve.streamer import MastodonStreamer
from mastodon_retrieve import MastodonHarvester, MastodonSearchParams

pytestmark = pytest.mark.integration


@pytest.fixture()
def mastodon_dates() -> tuple[datetime, datetime]:
    """
    Get sample start and end dates for testing the Mastodon API Harvester
    """
    start = datetime(2026, 4, 23, tzinfo=UTC)
    end = datetime(2026, 4, 26, tzinfo=UTC)
    return start, end


def test_initialisation(mastodon_settings_no_auth):
    """
    Test initialisation of the mastodon harvester client.
    """

    with pytest.raises(AttributeError):
        MastodonHarvester(settings=mastodon_settings_no_auth)

    _ = MastodonHarvester()


def test_timeline_retrieve(mastodon_dates):
    """
    Test that results can be fetched from the public timeline within a given time range
    """
    harvester = MastodonHarvester()
    start, end = mastodon_dates
    params = MastodonSearchParams(timeline="public", limit=12)

    i = 0
    for result in harvester.run(start, end, params=params):
        i += 1
        # Give some leeway to account for timezone
        post_date = result.edited_at or result.created_at
        assert start <= post_date, "Post created before start date"
        assert end >= result.created_at, "Post created after end date"

    assert i == params.limit, "Incorrect number of results"


def test_timeline_hashtag(mastodon_dates):
    """
    Test that getting data for a given hashtag returns results with the
    expected tag.
    """

    harvester = MastodonHarvester()
    start, end = mastodon_dates
    params = MastodonSearchParams(
        timeline="public", limit=24, hashtag="australia"
    )

    i = 0
    for result in harvester.run(start, end, params=params):
        # Give some leeway to account for timezone
        assert params.hashtag in {
            s.name.lower().strip() for s in result.tags
        }, "Missing hashtag!"
        i += 1

    assert i > 0, "Processed no results!"


@pytest.mark.asyncio
async def test_mastodon_stream_public():
    """
    Test that mastodon streaming from public timeline works properly.
    :return:
    """
    max_events = 16
    streamer = MastodonStreamer()

    count = 0
    # Don't want this to run forever
    async with asyncio.timeout(60):
        async for signal in streamer.stream_public_timeline(max_events):
            count += 1
            # Events can either be null (just meant to keep queues alive)
            # or Status objects parsed from the stream
            if signal:
                assert isinstance(signal, schemas.Status), (
                    "Expected parsed 'Status'"
                )

            if count >= max_events:
                break


@pytest.mark.asyncio
async def test_mastodon_stream_hashtag():
    """
    Test that mastodon streaming from hashtag timeline works properly.
    :return:
    """
    max_events = 16
    streamer = MastodonStreamer()

    count = 0
    try:
        async with asyncio.timeout(60):
            async for signal in streamer.stream_hashtag(
                "taylorswift", max_events
            ):
                count += 1
                # Events can either be null (just meant to keep queues alive)
                # or Status objects parsed from the stream
                if signal:
                    assert isinstance(signal, schemas.Status), (
                        "Expected parsed 'Status'"
                    )

                if count >= max_events:
                    break
    except asyncio.TimeoutError:
        # Hashtag timelines receive far fewer than public timelines, so this
        # might timeout before reaching the max number of posts
        print("Listener timed out")
