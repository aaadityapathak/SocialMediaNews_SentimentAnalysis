import json
import sys
import threading
import types
from contextlib import contextmanager
from unittest.mock import MagicMock

import pytest
from threads_retrieve import parse_thread
from threads_retrieve.parser import parse_page
from threads_retrieve.schemas import make_document, upload_to_elasticsearch
from threads_retrieve.scraper import scrape_keyword
from threads_retrieve.settings import ThreadsStreamSettings
from threads_retrieve.streamer import harvest_keywords


def raw_post(post_id="1"):
    return {
        "post": {
            "id": post_id,
            "caption": {"text": "Train news"},
            "code": "abc",
            "user": {"username": "reporter"},
            "video_versions": [{"url": "a"}, {"url": "a"}, {"url": "b"}],
        },
        "view_replies_cta_string": "1,234 replies",
    }


def test_parser_extracts_counts_and_stably_deduplicates_media():
    result = parse_thread(raw_post())
    assert result["reply_count"] == 1234
    assert result["videos"] == ["a", "b"]
    assert result["url"] == "https://www.threads.net/@reporter/post/abc"
    assert parse_thread(None) == {}


def test_page_parser_ignores_malformed_payloads_and_duplicate_posts():
    payload = {"nested": [{"thread_items": [raw_post(), None]}]}
    script = (
        '<script type="application/json">' + json.dumps(payload) + "</script>"
    )
    results = parse_page(
        '<script type="application/json">{bad thread_items}</script>'
        + script
        + script
    )
    assert len(results) == 1 and results[0]["id"] == "1"


def test_null_text_normalizes_without_failure():
    assert make_document({"text": None}, "train")["text"] == ""
    assert (
        make_document({"text": "train\nnews"}, "train")["text"] == "train news"
    )


def test_keyword_collection_deduplicates_keywords_and_posts(monkeypatch):
    searched = []
    uploaded = []

    def scrape(keyword, **kwargs):
        searched.append(keyword)
        return [
            {"id": "shared", "text": "news"},
            {"id": keyword, "text": keyword},
        ], False

    monkeypatch.setattr("threads_retrieve.streamer.scrape_keyword", scrape)

    def upload(client, documents, index):
        uploaded.extend(documents)
        return len(documents)

    monkeypatch.setattr(
        "threads_retrieve.streamer.upload_to_elasticsearch", upload
    )
    result = harvest_keywords(
        object(), ThreadsStreamSettings(keywords=["a", "a", "b"], max_workers=1)
    )
    assert searched == ["a", "b"]
    assert {item["post_id"] for item in uploaded} == {"shared", "a", "b"}
    assert result.total_added == 3 and not result.interrupted


def test_block_prevents_later_keywords(monkeypatch):
    searched = []

    def scrape(keyword, **kwargs):
        searched.append(keyword)
        return [], True

    monkeypatch.setattr("threads_retrieve.streamer.scrape_keyword", scrape)
    result = harvest_keywords(
        object(), ThreadsStreamSettings(keywords=["a", "b", "c"], max_workers=1)
    )
    assert searched == ["a"]
    assert result.interrupted and result.total_added == 0


def test_worker_failure_surfaces_instead_of_false_success(monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError("browser is missing")

    monkeypatch.setattr("threads_retrieve.streamer.scrape_keyword", fail)
    with pytest.raises(RuntimeError, match="Threads harvest failed") as exc:
        harvest_keywords(
            object(), ThreadsStreamSettings(keywords=["a"], max_workers=1)
        )
    assert str(exc.value.__cause__) == "browser is missing"


def test_upload_streams_actions_and_surfaces_partial_failure(monkeypatch):
    captured = []

    def bulk(client, actions, **kwargs):
        captured.extend(actions)
        assert kwargs["max_retries"] == 3
        yield False, {}

    monkeypatch.setattr("threads_retrieve.schemas.helpers.streaming_bulk", bulk)
    with pytest.raises(RuntimeError, match="1 documents"):
        upload_to_elasticsearch(
            object(),
            iter(
                [{"post_id": "1", "text": "news"}, {"post_id": "2", "text": ""}]
            ),
            "threads",
        )
    assert len(captured) == 1 and captured[0]["_id"] == "1"


def fake_browser(monkeypatch):
    page = MagicMock()
    page.url = "https://www.threads.net/search"
    page.title.return_value = "Threads"
    page.evaluate.side_effect = range(100)
    page.content.return_value = (
        '<script type="application/json">'
        + json.dumps({"thread_items": [raw_post()]})
        + "</script>"
    )
    browser = MagicMock()
    browser.new_context.return_value.new_page.return_value = page
    playwright = MagicMock()
    playwright.chromium.launch.return_value = browser

    class Stealth:
        @contextmanager
        def use_sync(self, unused):
            yield playwright

    monkeypatch.setitem(
        sys.modules,
        "playwright_stealth",
        types.SimpleNamespace(Stealth=Stealth),
    )
    monkeypatch.setitem(
        sys.modules, "playwright", types.ModuleType("playwright")
    )
    monkeypatch.setitem(
        sys.modules,
        "playwright.sync_api",
        types.SimpleNamespace(sync_playwright=lambda: object()),
    )
    return page, browser


def test_browser_scroll_is_bounded_even_if_page_keeps_growing(monkeypatch):
    page, browser = fake_browser(monkeypatch)
    posts, blocked = scrape_keyword("trains & buses", max_scrolls=3)
    assert page.mouse.wheel.call_count == 3
    assert "q=trains+%26+buses" in page.goto.call_args.args[0]
    assert len(posts) == 1 and not blocked
    browser.close.assert_called_once()


def test_browser_closes_after_navigation_failure(monkeypatch):
    page, browser = fake_browser(monkeypatch)
    page.goto.side_effect = RuntimeError("navigation failed")
    with pytest.raises(RuntimeError, match="navigation failed"):
        scrape_keyword("trains")
    browser.close.assert_called_once()


def test_browser_stops_on_rate_limit(monkeypatch):
    page, browser = fake_browser(monkeypatch)
    stop = threading.Event()

    def navigate(*args, **kwargs):
        callback = page.on.call_args.args[1]
        callback(types.SimpleNamespace(status=429))

    page.goto.side_effect = navigate
    assert scrape_keyword("trains", stop_event=stop) == ([], True)
    assert stop.is_set()
    page.mouse.wheel.assert_not_called()
    browser.close.assert_called_once()


def test_scheduler_bounds_unconsumed_futures_and_uploads_every_keyword(
    monkeypatch,
):
    from threads_retrieve import streamer

    original_executor = streamer.concurrent.futures.ThreadPoolExecutor
    state = {"submitted": 0, "consumed": 0, "peak": 0}

    class TrackingExecutor(original_executor):
        def submit(self, *args, **kwargs):
            outstanding = state["submitted"] - state["consumed"]
            assert outstanding < self._max_workers
            state["submitted"] += 1
            state["peak"] = max(state["peak"], outstanding + 1)
            future = super().submit(*args, **kwargs)
            original_result = future.result

            def result(*args, **kwargs):
                try:
                    return original_result(*args, **kwargs)
                finally:
                    state["consumed"] += 1

            future.result = result
            return future

    monkeypatch.setattr(
        streamer.concurrent.futures, "ThreadPoolExecutor", TrackingExecutor
    )
    monkeypatch.setattr(
        streamer,
        "scrape_keyword",
        lambda keyword, **kwargs: ([{"id": keyword, "text": "news"}], False),
    )
    monkeypatch.setattr(
        streamer,
        "upload_to_elasticsearch",
        lambda client, documents, index: len(documents),
    )
    result = harvest_keywords(
        object(),
        ThreadsStreamSettings(
            keywords=[str(i) for i in range(12)], max_workers=2
        ),
    )
    assert result.total_added == 12
    assert state["submitted"] == state["consumed"] == 12
    assert state["peak"] <= 2


def test_scheduler_does_not_submit_more_work_after_upload_failure(monkeypatch):
    from threads_retrieve import streamer

    original_executor = streamer.concurrent.futures.ThreadPoolExecutor
    submitted = []

    class TrackingExecutor(original_executor):
        def submit(self, func, keyword, *args):
            submitted.append(keyword)
            return super().submit(func, keyword, *args)

    monkeypatch.setattr(
        streamer.concurrent.futures, "ThreadPoolExecutor", TrackingExecutor
    )
    monkeypatch.setattr(
        streamer,
        "scrape_keyword",
        lambda keyword, **kwargs: ([{"id": keyword, "text": "news"}], False),
    )

    def failed_upload(*args):
        raise RuntimeError("index failed")

    monkeypatch.setattr(streamer, "upload_to_elasticsearch", failed_upload)
    with pytest.raises(RuntimeError, match="Threads harvest failed"):
        harvest_keywords(
            object(),
            ThreadsStreamSettings(keywords=["a", "b", "c"], max_workers=1),
        )
    assert submitted == ["a"]


def test_scheduler_stops_submitting_at_deadline(monkeypatch):
    from threads_retrieve import streamer

    original_executor = streamer.concurrent.futures.ThreadPoolExecutor
    submitted = []
    clock = {"now": 0}

    class TrackingExecutor(original_executor):
        def submit(self, func, keyword, *args):
            submitted.append(keyword)
            return super().submit(func, keyword, *args)

    monkeypatch.setattr(
        streamer.concurrent.futures, "ThreadPoolExecutor", TrackingExecutor
    )
    monkeypatch.setattr(
        streamer, "time", types.SimpleNamespace(monotonic=lambda: clock["now"])
    )

    def scrape(keyword, **kwargs):
        clock["now"] = 10
        return [], False

    monkeypatch.setattr(streamer, "scrape_keyword", scrape)
    result = harvest_keywords(
        object(),
        ThreadsStreamSettings(
            keywords=["a", "b", "c"], max_workers=1, harvest_timeout_seconds=5
        ),
    )
    assert result.interrupted
    assert submitted == ["a"]
