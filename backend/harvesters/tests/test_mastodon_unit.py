"""Offline regressions for Mastodon pagination, SSE framing and deadlines."""

import asyncio
import json
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import httpx
import pytest

from mastodon_retrieve import streamer as streaming
from mastodon_retrieve.mastodon_harvest import (
    MastodonHarvester,
    MastodonSearchParams,
)
from mastodon_retrieve.settings import MastodonSettings


def status_json():
    return json.dumps(
        {
            "id": "100",
            "visibility": "public",
            "uri": "https://example.test/post/100",
            "url": None,
            "account": {
                "id": "1",
                "username": "alice",
                "acct": "alice",
                "locked": False,
                "bot": False,
                "created_at": "2026-01-01T00:00:00Z",
            },
            "created_at": "2026-01-01T00:00:00Z",
            "sensitive": False,
            "content": "<p>Australia</p>",
        }
    )


async def lines(values):
    for value in values:
        yield value


@pytest.mark.asyncio
async def test_sse_comments_metadata_and_multiline_data():
    data = status_json().split(", ", 1)
    events = [
        "event:update",
        ": heartbeat",
        "id: 1",
        "data: " + data[0] + ",",
        "data: " + data[1],
        "",
        "event: delete",
        "data: 100",
        "",
    ]
    result = [
        s
        async for s in streaming.MastodonStreamer().statuses_from_event_stream(
            lines(events)
        )
    ]
    statuses = [s for s in result if s]
    assert len(statuses) == 1
    assert statuses[0].content.strip() == "Australia"
    assert statuses[0].url is None


@pytest.mark.asyncio
async def test_bad_event_does_not_poison_following_event():
    result = [
        s
        async for s in streaming.MastodonStreamer().statuses_from_event_stream(
            lines(
                [
                    "event: update",
                    "data: invalid",
                    "",
                    "event: update",
                    "data: " + status_json(),
                    "",
                ]
            )
        )
    ]
    assert result[0] is None
    assert result[1].id == "100"


@pytest.mark.asyncio
@pytest.mark.parametrize("hashtag", [None, "australia"])
async def test_idle_stream_deadline_closes_iterator(monkeypatch, hashtag):
    closed = []

    async def idle(*args, **kwargs):
        try:
            await asyncio.Event().wait()
            yield None
        finally:
            closed.append(True)

    monkeypatch.setattr(
        streaming.MastodonStreamer, "stream_public_timeline", idle
    )
    monkeypatch.setattr(streaming.MastodonStreamer, "stream_hashtag", idle)
    vk = Mock(lpush=AsyncMock())
    assert (
        await streaming.MastodonStreamer().stream_to_vk(
            vk, max_time=0.01, hashtag=hashtag
        )
        == 0
    )
    assert closed == [True]


@pytest.mark.asyncio
async def test_http_failures_are_retried_and_status_checked(monkeypatch):
    calls = []

    def handle(request):
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(503)
        return httpx.Response(
            200, text="event: update\ndata: " + status_json() + "\n\n"
        )

    client = httpx.AsyncClient
    monkeypatch.setattr(
        streaming.httpx,
        "AsyncClient",
        lambda **kwargs: client(
            transport=httpx.MockTransport(handle), **kwargs
        ),
    )
    monkeypatch.setattr(streaming.asyncio, "sleep", AsyncMock())
    streamer = streaming.MastodonStreamer(
        settings=MastodonSettings(
            base_url="https://example.test", auth_token=None
        )
    )
    result = [
        s
        async for s in streamer.stream_hashtag(
            "#australia", max_elements=1, local=True
        )
    ]
    assert result[0].id == "100"
    assert len(calls) == 2
    assert calls[0].url.path == "/api/v1/streaming/hashtag/local"
    assert "authorization" not in calls[0].headers
    assert calls[0].url.params["tag"] == "australia"


@pytest.mark.asyncio
async def test_queue_timeout_propagates(monkeypatch):
    async def source(*args, **kwargs):
        async for (
            item
        ) in streaming.MastodonStreamer().statuses_from_event_stream(
            lines(
                [
                    "event: update",
                    "data: " + status_json(),
                    "",
                ]
            )
        ):
            yield item

    monkeypatch.setattr(
        streaming.MastodonStreamer, "stream_public_timeline", source
    )
    vk = Mock(lpush=AsyncMock(side_effect=TimeoutError("queue failed")))
    with pytest.raises(TimeoutError, match="queue failed"):
        await streaming.MastodonStreamer().stream_to_vk(vk, max_time=1)


def make_status(ident, day):
    return SimpleNamespace(
        id=str(ident),
        created_at=datetime(2026, 1, day, tzinfo=UTC),
        edited_at=None,
    )


@pytest.fixture
def harvester(monkeypatch):
    client = Mock()
    monkeypatch.setattr(
        "mastodon_retrieve.mastodon_harvest.Mastodon", lambda **kwargs: client
    )
    return MastodonHarvester(MastodonSettings(auth_token="test"))


def test_pagination_limit_counts_only_in_range_and_does_not_fetch_extra_page(
    harvester,
):
    harvester.client.timeline.return_value = [
        make_status(4, 4),
        make_status(3, 3),
        make_status(2, 2),
    ]
    result = list(
        harvester.run(
            datetime(2026, 1, 1, tzinfo=UTC),
            datetime(2026, 1, 3, tzinfo=UTC),
            params=MastodonSearchParams(limit=1),
        )
    )
    assert [r.id for r in result] == ["3"]
    harvester.client.fetch_next.assert_not_called()
    assert harvester.client.timeline.call_args.kwargs["limit"] == 40


def test_overlapping_pages_are_deduplicated_and_repeated_page_stops(harvester):
    harvester.client.timeline.return_value = [
        make_status(5, 5),
        make_status(4, 4),
    ]
    harvester.client.fetch_next.side_effect = [
        [make_status(4, 4), make_status(3, 3)],
        [make_status(4, 4), make_status(3, 3)],
    ]
    result = list(
        harvester.run(
            datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 1, 8, tzinfo=UTC)
        )
    )
    assert [r.id for r in result] == ["5", "4", "3"]
    assert harvester.client.fetch_next.call_count == 2


def test_invalid_window_and_zero_limit_do_not_request(harvester):
    start = datetime(2026, 1, 1, tzinfo=UTC)
    end = datetime(2026, 1, 8, tzinfo=UTC)
    with pytest.raises(ValueError):
        list(harvester.run(end, start))
    assert (
        list(harvester.run(start, end, params=MastodonSearchParams(limit=0)))
        == []
    )
    harvester.client.timeline.assert_not_called()


def test_context_manager_closes_http_session(harvester):
    with harvester as opened:
        assert opened is harvester
    harvester.client.session.close.assert_called_once()


def test_fission_entrypoint_closes_valkey(monkeypatch):
    import mastodon_fission

    settings = MastodonSettings()
    monkeypatch.setattr(
        mastodon_fission,
        "read_from_secret",
        lambda name, cls: (
            settings
            if cls is MastodonSettings
            else SimpleNamespace(host="localhost", port=6379)
        ),
    )
    client = AsyncMock()
    client.__aenter__.return_value = client
    monkeypatch.setattr(mastodon_fission, "Valkey", Mock(return_value=client))
    monkeypatch.setattr(
        mastodon_fission.MastodonStreamer,
        "stream_to_vk",
        AsyncMock(return_value=2),
    )
    assert mastodon_fission.mastodon_au() == {"total_added": 2}
    client.__aexit__.assert_awaited_once()


@pytest.mark.asyncio
async def test_deadline_during_queue_write_reports_unconfirmed_delivery(
    monkeypatch,
):
    async def source(*args, **kwargs):
        async for (
            item
        ) in streaming.MastodonStreamer().statuses_from_event_stream(
            lines(
                [
                    "event: update",
                    "data: " + status_json(),
                    "",
                ]
            )
        ):
            yield item

    async def slow_publish(*args):
        await asyncio.Event().wait()

    monkeypatch.setattr(
        streaming.MastodonStreamer, "stream_public_timeline", source
    )
    vk = Mock(lpush=AsyncMock(side_effect=slow_publish))
    with pytest.raises(TimeoutError, match="delivery is unconfirmed"):
        await streaming.MastodonStreamer().stream_to_vk(vk, max_time=0.01)
    vk.lpush.assert_awaited_once()
