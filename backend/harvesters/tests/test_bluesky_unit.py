"""Offline regressions for JetStream and historical Bluesky ingestion."""

import asyncio
import json
from datetime import timedelta
from unittest.mock import AsyncMock, Mock

import httpx
import pytest

from bluesky import streamer as live
from bluesky_historical.bluesky_historical import (
    BlueskyHistoricalCollector,
    BlueskyHistoricalSettings,
)


def event(key="1", text="Australia train news", did="did:plc:alice"):
    return json.dumps(
        {
            "did": did,
            "time_us": int(key),
            "kind": "commit",
            "commit": {
                "operation": "create",
                "collection": "app.bsky.feed.post",
                "rkey": key,
                "record": {"text": text, "createdAt": "2026-01-01T00:00:00Z"},
            },
        }
    )


class Socket:
    def __init__(self, messages):
        self.messages = iter(messages)
        self.closed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        self.closed = True

    async def recv(self):
        try:
            message = next(self.messages)
        except StopIteration:
            await asyncio.Event().wait()
        if isinstance(message, Exception):
            raise message
        return message


@pytest.mark.asyncio
async def test_whitelist_uses_did_ttl_and_honours_topic_and_limit(monkeypatch):
    socket = Socket(
        [
            event("1", "Nothing about transport"),
            event("2", "train news"),
            event("3"),
        ]
    )
    monkeypatch.setattr(live.websockets, "connect", lambda *_: socket)
    vk = Mock(exists=AsyncMock(return_value=1), set=AsyncMock())
    streamer = live.BlueskyStreamer()
    posts = [
        post
        async for post in streamer.stream_posts(
            vk, max_elements=1, keywords=["train"]
        )
    ]
    assert [p.commit.rkey for p in posts if p] == ["2"]
    vk.exists.assert_awaited_once_with("bsky:whitelist:did:plc:alice")
    assert socket.closed
    await streamer.whitelist_account("did:plc:alice", vk)
    assert vk.set.await_args.kwargs["ex"] == timedelta(days=7)


@pytest.mark.asyncio
async def test_invalid_events_are_skipped_and_valid_posts_do_not_lookup_whitelist(
    monkeypatch,
):
    socket = Socket(["invalid", "[]", "{}", event()])
    monkeypatch.setattr(live.websockets, "connect", lambda *_: socket)
    vk = Mock(exists=AsyncMock(), set=AsyncMock())
    posts = [
        p async for p in live.BlueskyStreamer().stream_posts(vk, max_elements=1)
    ]
    assert len([p for p in posts if p]) == 1
    vk.exists.assert_not_awaited()
    vk.set.assert_awaited_once()


@pytest.mark.asyncio
async def test_reconnect_resumes_cursor(monkeypatch):
    connections = [
        Socket([event(), OSError("disconnect")]),
        Socket([event("2")]),
    ]
    connect = Mock(side_effect=connections)
    monkeypatch.setattr(live.websockets, "connect", connect)
    monkeypatch.setattr(live.asyncio, "sleep", AsyncMock())
    vk = Mock(set=AsyncMock())
    posts = [
        p async for p in live.BlueskyStreamer().stream_posts(vk, max_elements=2)
    ]
    assert len(posts) == 2
    assert "cursor=1" in connect.call_args.args[0]
    assert all(s.closed for s in connections)


@pytest.mark.asyncio
async def test_idle_stream_deadline_closes_socket(monkeypatch):
    socket = Socket([])
    monkeypatch.setattr(live.websockets, "connect", lambda *_: socket)
    vk = Mock(lpush=AsyncMock())
    assert await live.BlueskyStreamer().stream_to_vk(vk, max_time=0.01) == 0
    assert socket.closed
    vk.lpush.assert_not_awaited()


@pytest.mark.asyncio
async def test_sink_failure_is_not_reported_as_success(monkeypatch):
    socket = Socket([event()])
    monkeypatch.setattr(live.websockets, "connect", lambda *_: socket)
    vk = Mock(
        set=AsyncMock(),
        lpush=AsyncMock(side_effect=TimeoutError("queue failed")),
    )
    with pytest.raises(TimeoutError, match="queue failed"):
        await live.BlueskyStreamer().stream_to_vk(vk, max_time=1)
    assert socket.closed


def test_keywords_preserve_word_boundaries_and_empty_text():
    assert not live.is_au_relevant("Australianism and a ballroom")
    assert live.is_au_relevant("Australia")
    assert live.is_au_relevant("Melbourne and Sydney")
    assert not live.is_au_relevant("Melbourne")
    assert not live.is_au_relevant(None)


@pytest.fixture
def collector(tmp_path):
    settings = BlueskyHistoricalSettings(
        handle="test",
        app_password="secret",
        checkpoint_path=str(tmp_path / "checkpoint.json"),
    )
    es = Mock(mget=AsyncMock())
    vk = Mock(llen=AsyncMock(return_value=0), lpush=AsyncMock())
    return BlueskyHistoricalCollector(settings, es, vk)


def doc(key):
    return json.loads(event(str(key)))


@pytest.mark.asyncio
async def test_historical_batches_existence_and_queue_operations(collector):
    collector.es.mget.return_value = {
        "docs": [{"found": True}, {"found": False}]
    }
    assert await collector.index_batch([doc(1), doc(2), doc(2)]) == 1
    collector.es.mget.assert_awaited_once_with(
        index="social-posts-index",
        ids=["bluesky-did:plc:alice:1", "bluesky-did:plc:alice:2"],
        source=False,
    )
    collector.vk.lpush.assert_awaited_once()
    assert (
        json.loads(collector.vk.lpush.await_args.args[1])["data"]["commit"][
            "rkey"
        ]
        == "2"
    )
    # Pending items from another query are suppressed before the next ES read.
    assert await collector.index_batch([doc(2)]) == 0
    assert collector.es.mget.await_count == 1


@pytest.mark.asyncio
async def test_historical_bulk_missing_or_error_results_fail_closed(collector):
    collector.es.mget.return_value = {"docs": [{"error": "unavailable"}]}
    with pytest.raises(RuntimeError, match="existing"):
        await collector.index_batch([doc(1)])
    collector.vk.lpush.assert_not_awaited()


@pytest.mark.asyncio
async def test_historical_queue_failure_can_be_retried(collector):
    collector.es.mget.return_value = {"docs": [{"found": False}]}
    collector.vk.lpush.side_effect = [RuntimeError("offline"), 1]
    with pytest.raises(RuntimeError, match="offline"):
        await collector.index_batch([doc(1)])
    assert await collector.index_batch([doc(1)]) == 1


@pytest.mark.asyncio
async def test_historical_retries_rate_limits_with_server_delay(
    collector, monkeypatch
):
    responses = iter(
        [
            httpx.Response(429, headers={"Retry-After": "4"}),
            httpx.Response(200, json={"posts": []}),
        ]
    )
    transport = httpx.MockTransport(lambda request: next(responses))
    sleep = AsyncMock()
    monkeypatch.setattr(
        "bluesky_historical.bluesky_historical.asyncio.sleep", sleep
    )
    async with httpx.AsyncClient(transport=transport) as client:
        assert await collector.fetch_page(client, "token", "Australia") == {
            "posts": []
        }
    sleep.assert_awaited_once_with(4)


@pytest.mark.asyncio
async def test_historical_non_retryable_http_error_propagates(collector):
    transport = httpx.MockTransport(lambda request: httpx.Response(401))
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(httpx.HTTPStatusError):
            await collector.fetch_page(client, "token", "Australia")


@pytest.mark.asyncio
async def test_historical_repeated_cursor_is_bounded(collector, monkeypatch):
    post = {
        "uri": "at://did:plc:alice/app.bsky.feed.post/1",
        "author": {"did": "did:plc:alice"},
        "record": {"text": "Australia", "createdAt": "2026-01-01T00:00:00Z"},
    }
    collector.fetch_page = AsyncMock(
        return_value={"posts": [post], "cursor": "same"}
    )
    monkeypatch.setattr(
        "bluesky_historical.bluesky_historical.asyncio.sleep", AsyncMock()
    )
    result = await collector.collect_query(
        Mock(), "token", "Australia", dry_run=True
    )
    assert result["pages"] == 2
    assert collector.fetch_page.await_count == 2
    assert (
        json.loads(
            __import__("pathlib")
            .Path(collector.settings.checkpoint_path)
            .read_text()
        )["status"]
        == "query_error"
    )


@pytest.mark.asyncio
async def test_historical_full_queue_fails_before_enqueue(collector):
    collector.settings.queue_wait_seconds = 0.01
    collector.vk.llen.return_value = collector.settings.queue_limit
    collector.es.mget.return_value = {"docs": [{"found": False}]}
    with pytest.raises(TimeoutError, match="remained full"):
        await collector.index_batch([doc(1)])
    collector.vk.lpush.assert_not_awaited()


@pytest.mark.asyncio
async def test_historical_batches_are_bounded(collector):
    collector.settings.batch_size = 2
    collector.es.mget.side_effect = [
        {"docs": [{"found": False}, {"found": False}]},
        {"docs": [{"found": False}]},
    ]
    assert await collector.index_batch([doc(1), doc(2), doc(3)]) == 3
    assert [
        len(call.kwargs["ids"]) for call in collector.es.mget.await_args_list
    ] == [2, 1]
    assert [
        len(call.args) - 1 for call in collector.vk.lpush.await_args_list
    ] == [2, 1]


@pytest.mark.asyncio
async def test_stream_cli_uses_queue_client_and_closes_it(monkeypatch):
    from bluesky import __main__ as cli

    client = AsyncMock()
    client.__aenter__.return_value = client
    monkeypatch.setattr(cli, "Valkey", Mock(return_value=client))
    deliver = AsyncMock(return_value=4)
    monkeypatch.setattr(cli.BlueskyStreamer, "stream_to_vk", deliver)
    assert await cli.stream_records(keywords="train;bus") == {"total_added": 4}
    assert deliver.await_args.args[0] is client
    assert deliver.await_args.kwargs["queue"] == "social-posts-index"
    client.__aexit__.assert_awaited_once()


@pytest.mark.asyncio
async def test_historical_partial_failures_remain_visible_in_final_summary(
    collector,
):
    collector.create_session = AsyncMock(return_value="token")
    collector.fetch_page = AsyncMock(
        side_effect=[RuntimeError("provider failed"), {"posts": []}]
    )
    result = await collector.collect(["Australia", "Melbourne"], dry_run=True)
    assert result["failed_queries"] == 1
    assert result["failed_windows"] == 1
    assert result["queries"] == 2
    checkpoint = json.loads(
        __import__("pathlib")
        .Path(collector.settings.checkpoint_path)
        .read_text()
    )
    assert checkpoint["status"] == "collection_partial"
    assert checkpoint["failed_queries"] == 1


@pytest.mark.asyncio
async def test_historical_sink_failure_marks_window_incomplete(collector):
    collector.collect_query = AsyncMock(side_effect=RuntimeError("sink failed"))
    result = await collector.collect_window(
        Mock(), "token", ["Australia"], None, None
    )
    assert result["failed_queries"] == result["failed_windows"] == 1
    checkpoint = json.loads(
        __import__("pathlib")
        .Path(collector.settings.checkpoint_path)
        .read_text()
    )
    assert checkpoint["status"] == "window_partial"


@pytest.mark.asyncio
async def test_historical_strict_mode_stops_on_failure(collector):
    collector.settings.continue_on_error = False
    collector.create_session = AsyncMock(return_value="token")
    collector.fetch_page = AsyncMock(
        side_effect=RuntimeError("provider failed")
    )
    with pytest.raises(RuntimeError, match="provider failed"):
        await collector.collect(["Australia"], dry_run=True)


def test_historical_id_matches_live_processor_format(collector):
    post = {
        "uri": "at://did:plc:alice/app.bsky.feed.post/1",
        "author": {"did": "did:plc:alice", "handle": "alice.test"},
        "record": {"text": "Australia", "createdAt": "2026-01-01T00:00:00Z"},
    }
    normalised = collector.normalise_post(post, [])
    assert "uri" not in normalised
    assert collector.make_doc_id(normalised) == "did:plc:alice:1"


@pytest.mark.asyncio
async def test_deadline_during_queue_write_reports_unconfirmed_delivery(
    monkeypatch,
):
    socket = Socket([event()])
    monkeypatch.setattr(live.websockets, "connect", lambda *_: socket)

    async def slow_publish(*args):
        await asyncio.Event().wait()

    vk = Mock(set=AsyncMock(), lpush=AsyncMock(side_effect=slow_publish))
    with pytest.raises(TimeoutError, match="delivery is unconfirmed"):
        await live.BlueskyStreamer().stream_to_vk(vk, max_time=0.01)
    vk.lpush.assert_awaited_once()
    assert socket.closed
