"""Offline regression coverage for YouTube ingestion and publication."""

import copy
import json
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, call

import pytest
from googleapiclient.errors import HttpError
from httplib2 import Response
from youtube import YoutubeHarvester, YoutubeSearchParams
from youtube.api import iter_items
from youtube.records import comment_record, reply_record
from youtube.settings import YoutubeSettings
from youtube.streamer import YoutubeStreamer

START = datetime(2026, 1, 1, tzinfo=UTC)
END = datetime(2026, 1, 2, tzinfo=UTC)


def api_resource(*responses):
    resource = MagicMock()
    resource.list.return_value.execute.side_effect = responses
    return resource


def search_video(video_id):
    return {
        "id": {"videoId": video_id},
        "snippet": {
            "title": "Title",
            "channelTitle": "Channel",
            "channelId": "channel-1",
            "description": "Description",
            "publishedAt": "2026-01-01T12:00:00Z",
        },
    }


def thread(
    comment_id, published="2026-01-01T12:00:00Z", total_replies=0, replies=()
):
    return {
        "snippet": {
            "topLevelComment": {
                "id": comment_id,
                "snippet": {"textOriginal": "hello", "publishedAt": published},
            },
            "totalReplyCount": total_replies,
        },
        "replies": {"comments": list(replies)},
    }


def http_error(reason, status=403):
    return HttpError(
        Response({"status": status}),
        json.dumps({"error": {"errors": [{"reason": reason}]}}).encode(),
    )


def test_pagination_caps_each_request_and_stops_at_limit():
    resource = api_resource(
        {"items": list(range(50)), "nextPageToken": "page2"},
        {"items": list(range(50, 65)), "nextPageToken": "page3"},
    )
    assert list(iter_items(resource, limit=55, page_size=50)) == list(range(55))
    assert resource.list.call_args_list == [
        call(maxResults=50),
        call(maxResults=5, pageToken="page2"),
    ]
    assert resource.list.return_value.execute.call_args_list == [
        call(num_retries=3),
        call(num_retries=3),
    ]


def test_pagination_stops_on_repeated_token():
    resource = api_resource(
        {"items": [1], "nextPageToken": "same"},
        {"items": [2], "nextPageToken": "same"},
    )
    assert list(iter_items(resource, limit=100, page_size=50)) == [1, 2]
    assert resource.list.call_count == 2


def test_search_and_statistics_use_bounded_batches_and_cache():
    client = MagicMock()
    client.search.return_value = api_resource(
        {
            "items": [search_video(str(i)) for i in range(50)],
            "nextPageToken": "second",
        },
        {"items": [search_video(str(i)) for i in range(50, 55)]},
    )
    client.videos.return_value = api_resource(
        {
            "items": [
                {"id": str(i), "statistics": {"commentCount": "2"}}
                for i in range(50)
            ]
        },
        {
            "items": [
                {"id": str(i), "statistics": {"commentCount": "2"}}
                for i in range(50, 55)
            ]
        },
    )
    harvester = YoutubeHarvester(
        client=client, search_params=YoutubeSearchParams(max_videos=55)
    )
    videos = harvester._get_videos("tram", START.isoformat(), END.isoformat())
    assert len(videos) == 55
    assert (
        len(client.videos().list.call_args_list[0].kwargs["id"].split(","))
        == 50
    )
    assert (
        len(client.videos().list.call_args_list[1].kwargs["id"].split(",")) == 5
    )
    assert harvester._filter_videos_without_comments(videos) == videos
    assert client.videos().list.call_count == 2


def test_comments_reuse_embedded_replies_without_mutating_response():
    reply = {"id": "reply-1", "snippet": {"textOriginal": "reply"}}
    response = {
        "items": [thread("comment-1", total_replies=1, replies=[reply])]
    }
    original = copy.deepcopy(response)
    client = MagicMock()
    client.commentThreads.return_value = api_resource(response)
    result = YoutubeHarvester(client=client)._get_comments("video-1")
    assert result[0]["replies"] == [
        {"textOriginal": "reply", "reply_id": "reply-1"}
    ]
    client.comments.assert_not_called()
    assert response == original


def test_partial_embedded_replies_fetch_full_page_and_respect_limit():
    client = MagicMock()
    client.commentThreads.return_value = api_resource(
        {"items": [thread("c1", total_replies=6)]}
    )
    client.comments.return_value = api_resource(
        {
            "items": [
                {"id": str(i), "snippet": {"textOriginal": str(i)}}
                for i in range(6)
            ]
        }
    )
    params = YoutubeSearchParams(max_replies=3)
    comments = YoutubeHarvester(
        client=client, search_params=params
    )._get_comments("video-1")
    assert len(comments[0]["replies"]) == 3
    assert client.comments().list.call_args.kwargs["maxResults"] == 3


def test_comments_keep_time_order_on_later_pages():
    client = MagicMock()
    client.commentThreads.return_value = api_resource(
        {"items": [thread("c1")], "nextPageToken": "next"},
        {"items": [thread("c2")]},
    )
    comments = YoutubeHarvester(client=client)._get_comments("video-1")
    assert [c["comment_id"] for c in comments] == ["c1", "c2"]
    assert all(
        c.kwargs["order"] == "time"
        for c in client.commentThreads().list.call_args_list
    )


def test_comments_stop_at_utc_cutoff_without_fetching_older_pages():
    client = MagicMock()
    client.commentThreads.return_value = api_resource(
        {
            "items": [
                thread("new", "2026-01-01T02:00:00+01:00"),
                thread("old", "2026-01-01T00:30:00+01:00"),
            ],
            "nextPageToken": "older",
        }
    )
    comments = YoutubeHarvester(client=client)._get_comments(
        "video-1", START.isoformat()
    )
    assert [c["comment_id"] for c in comments] == ["new"]
    assert client.commentThreads().list.call_count == 1


@pytest.mark.parametrize(
    "reason", ["quotaExceeded", "keyInvalid", "backendError"]
)
def test_api_failures_propagate_instead_of_reporting_success(reason):
    client = MagicMock()
    client.commentThreads.return_value = api_resource(http_error(reason))
    with pytest.raises(HttpError):
        YoutubeHarvester(client=client)._get_comments("video-1")


def test_disabled_comments_are_an_expected_empty_result():
    client = MagicMock()
    client.commentThreads.return_value = api_resource(
        http_error("commentsDisabled")
    )
    assert YoutubeHarvester(client=client)._get_comments("video-1") == []


def test_duplicate_queries_and_video_ids_are_harvested_once(monkeypatch):
    harvester = YoutubeHarvester(client=MagicMock())
    videos = MagicMock(return_value=[{"video_id": "1"}, {"video_id": "1"}])
    comments = MagicMock(return_value=[])
    monkeypatch.setattr(harvester, "_get_videos", videos)
    monkeypatch.setattr(harvester, "_get_comments", comments)
    result = list(
        harvester.run(START, END, queries={"topic": ["tram", "tram", "train"]})
    )
    assert len(result) == 1
    assert videos.call_count == 2
    comments.assert_called_once()


def test_owned_client_is_closed_when_harvest_fails(monkeypatch):
    client = MagicMock()
    client.search.return_value = api_resource(http_error("quotaExceeded"))
    build = MagicMock(return_value=client)
    monkeypatch.setattr("youtube.youtube.build", build)
    harvester = YoutubeHarvester(api_key="test-key")
    with pytest.raises(HttpError):
        list(harvester.run(START, END, queries={"topic": ["tram"]}))
    client.close.assert_called_once()
    assert harvester._client is None
    assert build.call_args.kwargs["developerKey"] == "test-key"


def test_injected_client_remains_owned_by_caller():
    client = MagicMock()
    client.search.return_value = api_resource({"items": []})
    assert (
        list(
            YoutubeHarvester(client=client).run(
                START, END, queries={"t": ["q"]}
            )
        )
        == []
    )
    client.close.assert_not_called()


def test_invalid_and_empty_windows_do_not_connect():
    client = MagicMock()
    harvester = YoutubeHarvester(client=client)
    with pytest.raises(ValueError):
        list(harvester.run(END, START))
    assert list(harvester.run(START, END, queries={})) == []
    client.search.assert_not_called()


@pytest.mark.parametrize("name", ["max_videos", "max_comments", "max_replies"])
def test_negative_limits_rejected(name):
    with pytest.raises(ValueError):
        YoutubeSearchParams(**{name: -1})


def harvested_video():
    return {
        "video_id": "v1",
        "topic": "transport",
        "channel": "ch1",
        "published": START.isoformat(),
        "comments": [
            {
                "comment_id": "c1",
                "textOriginal": "hello",
                "replies": [{"reply_id": "r1", "textOriginal": "reply"}],
            }
        ],
    }


def test_public_comments_and_replies_preserve_display_text():
    # API-key requests do not receive author-only textOriginal fields.
    comment = {"comment_id": "c1", "textDisplay": "Public comment"}
    reply = {"reply_id": "r1", "textDisplay": "Public reply"}
    video = harvested_video()
    assert comment_record(comment, video)["text"] == "Public comment"
    assert reply_record(reply, comment, video)["text"] == "Public reply"


def test_author_text_takes_precedence_and_empty_original_falls_back():
    video = harvested_video()
    comment = {
        "comment_id": "c1",
        "textOriginal": "Original",
        "textDisplay": "Display",
    }
    assert comment_record(comment, video)["text"] == "Original"
    reply = {"reply_id": "r1", "textOriginal": "", "textDisplay": "Display"}
    assert reply_record(reply, comment, video)["text"] == "Display"


def test_streamer_batches_records_and_preserves_queue_contract(monkeypatch):
    harvester = MagicMock()
    harvester.run.return_value = (video for video in [harvested_video()])
    factory = MagicMock(return_value=harvester)
    monkeypatch.setattr("youtube.streamer.YoutubeHarvester", factory)
    monkeypatch.setenv("YOUTUBE_API_KEY", "original")
    vk = MagicMock()
    settings = YoutubeSettings(api_key="new-key", queue_batch_size=2)
    counts = YoutubeStreamer(settings).harvest_to_vk(vk, START, END)
    assert counts == {"videos": 1, "comments": 1, "replies": 1}
    assert [len(c.args) - 1 for c in vk.lpush.call_args_list] == [2, 1]
    messages = [
        json.loads(value)
        for c in vk.lpush.call_args_list
        for value in c.args[1:]
    ]
    assert [m["data"]["kind"] for m in messages] == [
        "video",
        "comment",
        "reply",
    ]
    assert all(m["source"] == "youtube" for m in messages)
    assert "comments" not in messages[0]["data"]["record"]
    assert messages[2]["data"]["record"]["comment_id"] == "c1"
    assert factory.call_args.kwargs["api_key"] == "new-key"
    import os

    assert os.environ["YOUTUBE_API_KEY"] == "original"


def test_publishing_failure_closes_harvest_generator(monkeypatch):
    closed = []

    def videos():
        try:
            yield harvested_video()
        finally:
            closed.append(True)

    harvester = MagicMock()
    harvester.run.return_value = videos()
    monkeypatch.setattr(
        "youtube.streamer.YoutubeHarvester", MagicMock(return_value=harvester)
    )
    vk = MagicMock()
    vk.lpush.side_effect = ConnectionError("queue unavailable")
    with pytest.raises(ConnectionError):
        YoutubeStreamer(YoutubeSettings(api_key="test")).harvest_to_vk(
            vk, START, END
        )
    assert closed == [True]


def test_empty_query_mapping_is_respected(monkeypatch):
    harvester = MagicMock()
    harvester.run.return_value = iter(())
    # Use a generator to exercise the same close contract as production.
    harvester.run.return_value = (item for item in ())
    monkeypatch.setattr(
        "youtube.streamer.YoutubeHarvester", MagicMock(return_value=harvester)
    )
    vk = MagicMock()
    assert YoutubeStreamer(YoutubeSettings(api_key="test")).harvest_to_vk(
        vk, START, END, queries={}
    ) == {
        "videos": 0,
        "comments": 0,
        "replies": 0,
    }
    assert harvester.run.call_args.kwargs["queries"] == {}
    vk.lpush.assert_not_called()


@pytest.mark.parametrize("fails", [False, True])
def test_fission_closes_valkey_on_success_and_failure(monkeypatch, fails):
    import youtube_fission

    vk = MagicMock()
    monkeypatch.setattr(youtube_fission, "Valkey", MagicMock(return_value=vk))
    monkeypatch.setattr(
        youtube_fission,
        "read_from_secret",
        MagicMock(
            side_effect=[
                SimpleNamespace(host="localhost", port=6379),
                YoutubeSettings(api_key="test"),
            ]
        ),
    )
    streamer = MagicMock()
    streamer.harvest_to_vk.return_value = {
        "videos": 1,
        "comments": 2,
        "replies": 3,
    }
    monkeypatch.setattr(
        youtube_fission, "YoutubeStreamer", MagicMock(return_value=streamer)
    )
    if fails:
        streamer.harvest_to_vk.side_effect = ConnectionError(
            "queue unavailable"
        )
        with pytest.raises(ConnectionError):
            youtube_fission.youtube_harvest()
    else:
        result = youtube_fission.youtube_harvest()
        assert result["videos"] == 1
        assert datetime.fromisoformat(result["start"]) < datetime.fromisoformat(
            result["end"]
        )
    vk.close.assert_called_once()
