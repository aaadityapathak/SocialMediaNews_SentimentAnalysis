import pytest
from datetime import datetime, UTC

from youtube import YoutubeHarvester

pytestmark = pytest.mark.integration


@pytest.fixture()
def youtube_dates() -> tuple[datetime, datetime]:
    start = datetime(2026, 4, 1, tzinfo=UTC)
    end = datetime(2026, 4, 28, tzinfo=UTC)
    return start, end


def test_initialisation(monkeypatch, youtube_dates):
    start, end = youtube_dates
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
    with pytest.raises(KeyError):
        next(iter(YoutubeHarvester().run(start, end)))

    _ = YoutubeHarvester()


def test_video_retrieve(youtube_dates):
    harvester = YoutubeHarvester()
    start, end = youtube_dates
    queries = {"transport": ["melbourne tram myki"]}

    results = list(harvester.run(start, end, queries=queries))

    assert len(results) > 0
    for video in results:
        assert "video_id" in video
        assert "title" in video
        assert "topic" in video
        assert "comments" in video
        published = datetime.fromisoformat(video["published"])
        assert start <= published <= end


def test_custom_queries(youtube_dates):
    harvester = YoutubeHarvester()
    start, end = youtube_dates
    queries = {"tourism": ["visiting melbourne australia"]}

    results = list(harvester.run(start, end, queries=queries))

    assert len(results) > 0
    for video in results:
        assert video["topic"] == "tourism"
