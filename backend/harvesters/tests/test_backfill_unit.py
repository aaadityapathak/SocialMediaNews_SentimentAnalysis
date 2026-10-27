"""Offline coverage for archive replay, bounded queues, and hydration."""

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import httpx
import pytest
from base.backfill import (
    BackfillPublisher,
    bluesky_ids,
    existing_ids,
    wait_for_capacity,
)


@pytest.fixture
def script():
    def load(name):
        path = Path(__file__).parents[1] / "scripts" / f"{name}.py"
        spec = importlib.util.spec_from_file_location(
            f"backfill_test_{name}", path
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    return load


def clients(found=()):
    vk, es = MagicMock(), MagicMock()
    vk.llen.return_value = 0
    es.mget.side_effect = lambda **kw: {
        "docs": [
            {"_id": ident, "found": ident in found}
            for ident in reversed(kw["ids"])
        ]
    }
    return vk, es


def records(count):
    return [((str(i), f"alias-{i}"), {"data": i}) for i in range(count)]


def mastodon_post(ident="1"):
    return {
        "id": ident,
        "uri": f"https://mastodon.au/users/test/statuses/{ident}",
        "visibility": "public",
        "created_at": "2026-01-01T00:00:00Z",
        "sensitive": False,
        "content": "Australia transport",
        "account": {
            "id": "a",
            "username": "test",
            "acct": "test",
            "locked": False,
            "bot": False,
            "created_at": "2025-01-01T00:00:00Z",
        },
    }


def test_bulk_publisher_reduces_requests_and_preserves_record_order():
    vk, es = clients({"alias-1"})
    publisher = BackfillPublisher(vk, es, batch_size=3)
    assert publisher.publish(records(7)) == 6
    assert es.mget.call_count == 3
    assert vk.lpush.call_count == 3
    values = [
        json.loads(value)["data"]
        for call in vk.lpush.call_args_list
        for value in call.args[1:]
    ]
    assert values == [0, 2, 3, 4, 5, 6]
    assert all(len(call.kwargs["ids"]) <= 6 for call in es.mget.call_args_list)
    es.exists.assert_not_called()


def test_publisher_deduplicates_within_and_between_batches():
    vk, es = clients()
    publisher = BackfillPublisher(vk, es, batch_size=2)
    assert publisher.publish(records(1) * 5) == 1
    assert publisher.publish(records(1)) == 0
    assert vk.lpush.call_count == 1


def test_legacy_numeric_aliases_do_not_merge_distinct_mastodon_instances():
    vk, es = clients()
    publisher = BackfillPublisher(vk, es, batch_size=1)
    documents = [
        (("mastodon-https://one.test/posts/1", "mastodon-1"), {"data": 1}),
        (("mastodon-https://two.test/posts/1", "mastodon-1"), {"data": 2}),
    ]
    assert publisher.publish(documents) == 2


def test_recent_dedup_cache_is_bounded():
    vk, es = clients()
    publisher = BackfillPublisher(vk, es, batch_size=2, recent_ids_limit=3)
    publisher.publish(records(10))
    assert len(publisher.recent) == 3


def test_ignore_existing_skips_elasticsearch_checks():
    vk, es = clients()
    assert (
        BackfillPublisher(vk, es, ignore_existing=True).publish(records(2)) == 2
    )
    es.mget.assert_not_called()


@pytest.mark.parametrize(
    "response",
    [
        {"docs": []},
        {"docs": [{"_id": "1", "error": {"type": "unavailable"}}]},
        {"docs": [{"_id": "wrong", "found": False}]},
    ],
)
def test_incomplete_existence_checks_fail_closed(response):
    es = MagicMock()
    es.mget.return_value = response
    with pytest.raises(RuntimeError):
        existing_ids(es, "idx", ["1"])


def test_queue_failure_does_not_mark_records_as_sent():
    vk, es = clients()
    vk.lpush.side_effect = ConnectionError("unavailable")
    publisher = BackfillPublisher(vk, es)
    with pytest.raises(ConnectionError):
        publisher.publish(records(1))
    assert not publisher.recent


def test_backpressure_wait_is_bounded_and_checks_batch_capacity(monkeypatch):
    vk = MagicMock()
    vk.llen.return_value = 9
    monkeypatch.setattr(
        "base.backfill.time.monotonic", MagicMock(side_effect=[0, 0, 2])
    )
    sleep = MagicMock()
    monkeypatch.setattr("base.backfill.time.sleep", sleep)
    with pytest.raises(TimeoutError):
        wait_for_capacity(
            vk, max_queue_length=10, pending=2, timeout=1, poll_interval=2
        )
    sleep.assert_called_once_with(1)


def test_backpressure_returns_when_queue_drains(monkeypatch):
    vk = MagicMock()
    vk.llen.side_effect = [10, 3]
    monkeypatch.setattr("base.backfill.time.sleep", MagicMock())
    wait_for_capacity(vk, max_queue_length=5, pending=2)
    assert vk.llen.call_count == 2


@pytest.mark.parametrize(
    "kwargs",
    [
        {"batch_size": 0},
        {"batch_size": 1001},
        {"queue_limit": 1},
        {"queue_wait_seconds": -1},
        {"recent_ids_limit": 0},
    ],
)
def test_invalid_publisher_settings_fail_early(kwargs):
    with pytest.raises(ValueError):
        BackfillPublisher(*clients(), **kwargs)


def test_bluesky_aliases_preserve_existing_uri_and_did_ids():
    uri = "at://did:plc:one/app.bsky.feed.post/key"
    assert set(bluesky_ids({"uri": uri})) == {
        f"bluesky-{uri}",
        "bluesky-did:plc:one:key",
    }
    assert set(
        bluesky_ids({"did": "did:plc:one", "commit": {"rkey": "key"}})
    ) == set(bluesky_ids({"uri": uri}))
    with pytest.raises(ValueError):
        bluesky_ids({"did": "did:plc:one"})


@pytest.mark.parametrize(
    "uri",
    [
        "bad",
        "https://did:plc:one/app.bsky.feed.post/key",
        "at://did:plc:one/wrong/key",
        "at://did:plc:one/app.bsky.feed.post/",
        None,
    ],
)
def test_hydration_rejects_malformed_uris(script, uri):
    with pytest.raises((ValueError, TypeError)):
        script("bluesky_hydrate")._parse_uri(uri)


def test_bluesky_index_backfill_checks_both_aliases_and_closes_clients(
    script, monkeypatch
):
    module = script("backfill_bluesky_idx")
    uri = "at://did:plc:one/app.bsky.feed.post/key"
    vk, es = clients({f"bluesky-{uri}"})
    monkeypatch.setattr(module, "get_clients", lambda: (vk, es))
    monkeypatch.setattr(
        module.helpers,
        "scan",
        lambda *args, **kw: (
            record
            for record in [
                {"_source": {"did": "did:plc:one", "commit": {"rkey": "key"}}},
                {
                    "_source": {
                        "did": "did:plc:two",
                        "commit": {"rkey": "other"},
                    }
                },
            ]
        ),
    )
    assert module.backfill_bsky_idx() == 1
    payload = json.loads(vk.lpush.call_args.args[1])
    assert payload["save_provider_idx"] is False
    assert "uri" not in payload["data"]
    vk.close.assert_called_once()
    es.close.assert_called_once()


def test_backfill_closes_scanner_and_clients_on_queue_failure(
    script, monkeypatch
):
    module = script("backfill_bluesky_idx")
    vk, es = clients()
    vk.lpush.side_effect = ConnectionError("queue down")
    monkeypatch.setattr(module, "get_clients", lambda: (vk, es))
    closed = []

    def scan(*args, **kwargs):
        try:
            yield {"_source": {"did": "did:plc:one", "commit": {"rkey": "key"}}}
        finally:
            closed.append(True)

    monkeypatch.setattr(module.helpers, "scan", scan)
    with pytest.raises(ConnectionError):
        module.backfill_bsky_idx(batch_size=1)
    assert closed == [True]
    vk.close.assert_called_once()
    es.close.assert_called_once()


def test_mastodon_index_replay_needs_no_provider_credentials(
    script, monkeypatch
):
    module = script("backfill_mastodon")
    vk, es = clients({"mastodon-1"})
    monkeypatch.setattr(module, "_get_storage_clients", lambda: (vk, es))
    provider = MagicMock(
        side_effect=AssertionError("must not instantiate Mastodon")
    )
    monkeypatch.setattr(module, "MastodonHarvester", provider)
    monkeypatch.setattr(
        module.helpers,
        "scan",
        lambda *args, **kw: (
            record
            for record in [
                {"_source": mastodon_post("1")},
                {"_source": mastodon_post("2")},
            ]
        ),
    )
    assert module.backfill_from_index(batch_size=2) == 1
    assert set(es.mget.call_args.kwargs["ids"]) == {
        "mastodon-1",
        "mastodon-2",
        f"mastodon-{mastodon_post('1')['uri']}",
        f"mastodon-{mastodon_post('2')['uri']}",
    }
    provider.assert_not_called()


def test_mastodon_api_replay_closes_provider_and_preserves_envelope(
    script, monkeypatch
):
    module = script("backfill_mastodon")
    vk, es = clients()
    ms = MagicMock()
    ms.run.return_value = (record for record in [mastodon_post()])
    monkeypatch.setattr(module, "get_clients", lambda: (ms, vk, es))
    assert module.backfill_from_api(batch_size=2) == 1
    assert es.mget.call_args.kwargs["index"] == "mastodon-idx"
    assert json.loads(vk.lpush.call_args.args[1])["save_provider_idx"] is True
    ms.close.assert_called_once()
    es.close.assert_called_once()
    vk.close.assert_called_once()


def test_hydration_refreshes_once_batches_and_filters_language(
    script, monkeypatch
):
    module = script("bluesky_hydrate")
    uri1, uri2 = (
        "at://did:plc:one/app.bsky.feed.post/key",
        "at://did:plc:two/app.bsky.feed.post/key",
    )
    request = httpx.Request("GET", "https://example.test")
    error = httpx.HTTPStatusError(
        "expired",
        request=request,
        response=httpx.Response(401, request=request),
    )
    posts = [
        {"uri": uri1, "record": {"text": "hello", "langs": ["en"]}},
        {"uri": uri1, "record": {"text": "duplicate"}},
        {"uri": uri2, "record": {"langs": ["fr"]}},
    ]
    fetch = MagicMock(side_effect=[error, posts])
    monkeypatch.setattr(module, "_get_posts", fetch)
    monkeypatch.setattr(
        module, "_create_session", MagicMock(return_value="refreshed")
    )
    vk, _ = clients()
    assert module._flush_batch(
        MagicMock(), "expired", [uri1, uri2], vk, "handle", "password"
    ) == ("refreshed", 1, 1)
    assert fetch.call_count == 2
    assert len(vk.lpush.call_args.args) == 2
    doc = json.loads(vk.lpush.call_args.args[1])["data"]
    assert doc["did"] == "did:plc:one"
    assert "uri" not in doc


def test_hydration_retries_transient_statuses_with_bounded_attempts(
    script, monkeypatch
):
    module = script("bluesky_hydrate")
    attempts = []

    def handler(request):
        attempts.append(request)
        return httpx.Response(503, json={"error": "busy"})

    monkeypatch.setattr(module.time, "sleep", MagicMock())
    with (
        httpx.Client(transport=httpx.MockTransport(handler)) as client,
        pytest.raises(httpx.HTTPStatusError),
    ):
        module._get_posts(
            client, "token", ["at://did:plc:one/app.bsky.feed.post/key"]
        )
    assert len(attempts) == 4


def test_hydration_batches_existing_checks_and_bounds_recent_cache(
    script, monkeypatch, tmp_path
):
    module = script("bluesky_hydrate")
    one = "at://did:plc:one/app.bsky.feed.post/key"
    two = "at://did:plc:two/app.bsky.feed.post/key"
    (tmp_path / "ids.json").write_text(
        json.dumps([one, two, one]), encoding="utf-8"
    )
    vk, es = clients({f"bluesky-{two}"})
    monkeypatch.setattr(module, "Valkey", MagicMock(return_value=vk))
    monkeypatch.setattr(module, "Elasticsearch", MagicMock(return_value=es))
    monkeypatch.setattr(
        module,
        "BlueskySettings",
        lambda: SimpleNamespace(handle="a", app_password="p"),
    )
    monkeypatch.setattr(
        module,
        "ESSettings",
        lambda: SimpleNamespace(host="https://example.test", api_key="k"),
    )
    monkeypatch.setattr(
        module, "_create_session", MagicMock(return_value="jwt")
    )
    flush = MagicMock(return_value=("jwt", 1, 0))
    monkeypatch.setattr(module, "_flush_batch", flush)
    assert module.hydrate(str(tmp_path), batch_size=2) == {
        "inserted": 1,
        "skipped_language": 0,
    }
    assert flush.call_args.args[2] == [one]
    assert es.mget.call_count == 1
    es.exists.assert_not_called()
    vk.close.assert_called_once()
    es.close.assert_called_once()


def test_spartan_streams_first_record_and_counts_invalid_rows(script, tmp_path):
    module = script("spartan_upload")
    path = tmp_path / "posts.ndjson"
    post = mastodon_post()
    post["createdAt"] = post.pop("created_at")
    post["account"]["createdAt"] = post["account"].pop("created_at")
    path.write_text(
        json.dumps({"doc": post}) + "\nnot-json\n", encoding="utf-8"
    )
    counts = {"processed": 0, "indexed": 0, "discarded": 0, "failed": 0}
    output = list(module._records(path, counts))
    assert len(output) == 1
    assert output[0][1]["data"]["id"] == "1"
    assert counts["processed"] == 2
    assert counts["failed"] == 1


def test_wait_queue_reuses_caller_client_and_times_out(script):
    module = script("wait_for_queue")
    vk = MagicMock()
    vk.llen.return_value = 100
    with pytest.raises(TimeoutError):
        module.wait_queue(silent=True, timeout=0, vk=vk)
    vk.close.assert_not_called()
