import io
import zipfile
from datetime import datetime
from unittest.mock import MagicMock

import pytest
import requests
from gdelt_retrieve.file_client import GdeltFileClient, create_session
from gdelt_retrieve.gdelt_harvest import EVENTS_SPEC, EventRecord, GkgRecord
from gdelt_retrieve.harvesters import EventsHarvester, GkgHarvester
from gdelt_retrieve.reader import iter_archive_rows
from gdelt_retrieve.schemas import (
    generate_actions_from_memory,
    upload_to_elasticsearch,
)
from gdelt_retrieve.settings import GdeltStreamSettings
from gdelt_retrieve.streamer import (
    get_latest_gdelt_timestamp,
    iter_joined_records,
    process_and_stream_batch,
)


def archive_bytes():
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("folder/", "")
        archive.writestr("folder/first.tsv", "a\tb\n")
        archive.writestr("second.tsv", "c\td\n")
    return output.getvalue()


def session_with_response(chunks):
    session = MagicMock()
    response = session.get.return_value.__enter__.return_value
    response.iter_content.return_value = chunks
    return session, response


def test_download_is_atomic_and_reuses_valid_cache(tmp_path):
    payload = archive_bytes()
    session, _response = session_with_response(
        [payload[:10], b"", payload[10:]]
    )
    client = GdeltFileClient(tmp_path, session=session)
    dest, ok = client.ensure_downloaded(EVENTS_SPEC, "20260101")
    assert ok and dest.read_bytes() == payload
    assert list(client.iter_rows(dest)) == [["a", "b"], ["c", "d"]]
    assert client.ensure_downloaded(EVENTS_SPEC, "20260101") == (dest, True)
    assert session.get.call_count == 1
    assert not list(dest.parent.glob("*.part"))
    session.get.return_value.__exit__.assert_called_once()


def test_failed_refresh_preserves_existing_archive_and_cleans_partial(tmp_path):
    dest = tmp_path / "archive.zip"
    dest.write_bytes(archive_bytes())
    original = dest.read_bytes()

    def interrupted():
        yield b"partial"
        raise requests.ConnectionError("interrupted")

    session, _ = session_with_response(interrupted())
    client = GdeltFileClient(tmp_path, session=session)
    assert client._stream_download("https://example.test", dest, "test") == (
        False,
        None,
    )
    assert dest.read_bytes() == original
    assert not list(tmp_path.glob("*.part"))


def test_corrupt_cache_is_downloaded_again(tmp_path):
    dest = tmp_path / "20260101" / EVENTS_SPEC.filename("20260101")
    dest.parent.mkdir()
    dest.write_bytes(b"not a zip")
    session, _ = session_with_response([archive_bytes()])
    assert GdeltFileClient(tmp_path, session).ensure_downloaded(
        EVENTS_SPEC, "20260101"
    )[1]
    assert zipfile.is_zipfile(dest)


def test_http_retry_policy_is_limited_to_safe_requests():
    with create_session() as session:
        retry = session.get_adapter("https://").max_retries
        assert retry.total == 3
        assert retry.allowed_methods == {"GET"}
        assert 429 in retry.status_forcelist and 503 in retry.status_forcelist


def test_raw_cleanup_and_session_close_when_consumer_stops(
    tmp_path, monkeypatch
):
    archive = tmp_path / "data.zip"
    archive.write_bytes(archive_bytes())
    client = MagicMock()
    client.__enter__.return_value = client
    client.ensure_downloaded.return_value = (archive, True)
    client.iter_rows.return_value = (row for row in [["a"], ["b"]])
    monkeypatch.setattr(
        "gdelt_retrieve.reader.GdeltFileClient", lambda _: client
    )
    rows = iter_archive_rows(
        tmp_path,
        datetime(2026, 1, 1),
        datetime(2026, 1, 1),
        "daily",
        EVENTS_SPEC,
        EVENTS_SPEC,
        delete_raw=True,
    )
    assert next(rows) == ["a"]
    rows.close()
    assert not archive.exists()
    client.__exit__.assert_called_once()


@pytest.mark.parametrize(
    "interval,start,end",
    [
        ("hourly", datetime(2026, 1, 1), datetime(2026, 1, 2)),
        ("daily", datetime(2026, 1, 2), datetime(2026, 1, 1)),
    ],
)
def test_invalid_ranges_fail_before_network(interval, start, end, tmp_path):
    with pytest.raises(ValueError):
        list(EventsHarvester(str(tmp_path)).run(start, end, interval))


def test_v2_events_are_mapped_without_mutating_source(monkeypatch):
    row = [str(i) for i in range(61)]
    row[37], row[38] = "AS", "AS07"
    original = row.copy()
    monkeypatch.setattr(
        "gdelt_retrieve.harvesters.iter_archive_rows",
        lambda *a, **k: (item for item in [row, ["bad"]]),
    )
    records = list(
        EventsHarvester().run(
            datetime(2026, 1, 1), datetime(2026, 1, 1), "15m", actor_cameo=None
        )
    )
    assert len(records) == 1
    assert records[0].Actor1Geo_Lat == "40"
    assert records[0].Actor2Geo_Lat == "48"
    assert records[0].ActionGeo_Lat == "56"
    assert records[0].SourceURL == "60"
    assert row == original


def test_gkg_without_location_allowed_when_filters_disabled(monkeypatch):
    row = [""] * 27
    row[1], row[4], row[7] = "20260101000000", "https://news.test", "THEME"
    monkeypatch.setattr(
        "gdelt_retrieve.harvesters.iter_archive_rows",
        lambda *a, **k: (item for item in [row]),
    )
    records = list(
        GkgHarvester().run(
            datetime(2026, 1, 1), datetime(2026, 1, 1), "15m", country_fips=None
        )
    )
    assert len(records) == 1 and records[0].SOURCEURLS == "https://news.test"


def test_join_keeps_all_events_sharing_url_and_deduplicates_gkg():
    rows = []
    for event_id in ("1", "2"):
        row = [""] * 58
        row[0], row[57] = event_id, "https://news.test/article"
        rows.append(EventRecord.from_row(row))
    gkg = GkgRecord.from_row(
        [
            "",
            "1",
            "",
            "A;B",
            "",
            "",
            "",
            "0,1,2,3",
            "",
            "",
            "https://news.test/article",
        ]
    )
    results = list(iter_joined_records(rows, [gkg, gkg], datetime(2026, 1, 1)))
    assert {item["GlobalEventID"] for item in results} == {"1", "2"}
    assert all(item["DateAdded"] == "20260101000000" for item in results)


def test_numeric_sanitization_preserves_zero_coordinates():
    action = next(
        generate_actions_from_memory(
            [
                {
                    "GlobalEventID": "1",
                    "SourceURL": "url",
                    "ActionGeo_Lat": "0",
                    "ActionGeo_Long": "0",
                    "AvgTone": "nan",
                    "NumMentions": "wrong",
                }
            ],
            "index",
        )
    )
    assert action["_source"]["ActionGeo_Location"] == "0.0,0.0"
    assert action["_source"]["AvgTone"] is None
    assert action["_source"]["NumMentions"] is None


def test_bulk_failure_is_reported(monkeypatch):
    monkeypatch.setattr(
        "gdelt_retrieve.schemas.helpers.streaming_bulk",
        lambda *a, **k: iter([(True, {}), (False, {})]),
    )
    with pytest.raises(RuntimeError, match="1 documents"):
        upload_to_elasticsearch(object(), iter([]))


def test_latest_manifest_parses_whitespace_and_event_entry(monkeypatch):
    session = MagicMock()
    session.__enter__.return_value = session
    response = session.get.return_value.__enter__.return_value
    response.text = "bad line\n1 hash https://data.test/20260101000000.gkg.csv.zip\n 2  hash  https://data.test/20260101001500.export.CSV.zip\n"
    monkeypatch.setattr(
        "gdelt_retrieve.streamer.create_session", lambda: session
    )
    assert get_latest_gdelt_timestamp(
        "https://data.test/lastupdate.txt"
    ) == datetime(2026, 1, 1, 0, 15)


def test_batch_honors_region_and_skips_gkg_without_events(
    tmp_path, monkeypatch
):
    events = MagicMock()
    events.run.return_value = iter([])
    gkg = MagicMock()
    monkeypatch.setattr(
        "gdelt_retrieve.streamer.EventsHarvester", lambda **k: events
    )
    monkeypatch.setattr("gdelt_retrieve.streamer.GkgHarvester", gkg)
    settings = GdeltStreamSettings(raw_dir=str(tmp_path), target_adm1="AS02")
    assert (
        process_and_stream_batch(datetime(2026, 1, 1), settings, object()) == 0
    )
    assert events.run.call_args.kwargs["adm1_code"] == "AS02"
    assert events.run.call_args.kwargs["raise_on_download_error"] is True
    gkg.assert_not_called()


def test_nonfinite_tone_and_long_document_id_are_safe():
    row = {
        "GlobalEventID": "1",
        "SourceURL": "https://news.test/" + "x" * 600,
        "GKG_TONE": "nan,2,bad,4",
    }
    action = next(generate_actions_from_memory([row], "index"))
    assert len(action["_id"]) == 64
    assert action["_source"]["GKG_Tone_Score"] is None
    assert action["_source"]["GKG_Tone_Positive"] == 2
    assert action["_source"]["GKG_Tone_Negative"] is None
    assert action["_source"]["GKG_Tone_Polarity"] == 4


def test_backfill_limits_inflight_days(monkeypatch):
    from concurrent.futures import Future

    from gdelt_retrieve.backfill import iter_backfill_results

    submitted = []

    class Executor:
        def __init__(self, max_workers):
            assert max_workers == 2

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def submit(self, function, day, *args):
            submitted.append(day)
            future = Future()
            future.set_result({"data": [], "msg": day.isoformat()})
            return future

    monkeypatch.setattr("gdelt_retrieve.backfill.ProcessPoolExecutor", Executor)
    results = iter_backfill_results(
        datetime(2026, 1, 1), datetime(2026, 1, 5), max_workers=2
    )
    first = next(results)
    assert len(submitted) == 2
    remaining = list(results)
    assert len(remaining) == 4
    assert len(submitted) == 5
    assert {day.day for day, result in [first, *remaining]} == {1, 2, 3, 4, 5}


def test_backfill_stops_after_upload_failure_and_preserves_backup(
    tmp_path, monkeypatch
):
    from types import SimpleNamespace

    from gdelt_retrieve.backfill import run_backfill

    calls = []

    def results(*args, **kwargs):
        for day in (1, 2):
            calls.append(day)
            yield (
                datetime(2026, 1, day),
                {
                    "data": [
                        {
                            "GlobalEventID": str(day),
                            "SourceURL": "https://news.test",
                        }
                    ],
                    "msg": "day",
                },
            )

    client = MagicMock()
    monkeypatch.setattr(
        "gdelt_retrieve.backfill.ESSettings",
        lambda: SimpleNamespace(host="https://example.test", api_key="test"),
    )
    monkeypatch.setattr(
        "gdelt_retrieve.backfill.Elasticsearch", lambda *args, **kwargs: client
    )
    monkeypatch.setattr(
        "gdelt_retrieve.backfill.iter_backfill_results", results
    )

    def fail(*args, **kwargs):
        raise RuntimeError("partial indexing failure")

    monkeypatch.setattr("gdelt_retrieve.backfill.upload_to_elasticsearch", fail)
    with pytest.raises(RuntimeError, match="partial indexing failure"):
        run_backfill(
            datetime(2026, 1, 1), datetime(2026, 1, 2), backup_dir=tmp_path
        )
    assert calls == [1]
    assert (tmp_path / "gdelt_20260101_daily.csv").is_file()
    client.__exit__.assert_called_once()


def test_missing_download_raises_for_scheduled_batches(tmp_path, monkeypatch):
    client = MagicMock()
    client.__enter__.return_value = client
    client.ensure_downloaded.return_value = (tmp_path / "missing.zip", False)
    monkeypatch.setattr(
        "gdelt_retrieve.reader.GdeltFileClient", lambda _: client
    )
    with pytest.raises(OSError, match="Could not download"):
        list(
            iter_archive_rows(
                tmp_path,
                datetime(2026, 1, 1),
                datetime(2026, 1, 1),
                "daily",
                EVENTS_SPEC,
                EVENTS_SPEC,
                raise_on_download_error=True,
            )
        )
    client.__exit__.assert_called_once()


def test_corrupt_zip_content_is_evicted_after_read_error(tmp_path, monkeypatch):
    archive = tmp_path / "corrupt.zip"
    archive.write_bytes(b"corrupt")
    client = MagicMock()
    client.__enter__.return_value = client
    client.ensure_downloaded.return_value = (archive, True)

    def rows():
        yield ["first"]
        raise zipfile.BadZipFile("bad CRC")

    client.iter_rows.return_value = rows()
    monkeypatch.setattr(
        "gdelt_retrieve.reader.GdeltFileClient", lambda _: client
    )
    stream = iter_archive_rows(
        tmp_path,
        datetime(2026, 1, 1),
        datetime(2026, 1, 1),
        "daily",
        EVENTS_SPEC,
        EVENTS_SPEC,
    )
    assert next(stream) == ["first"]
    with pytest.raises(zipfile.BadZipFile, match="bad CRC"):
        next(stream)
    assert not archive.exists()
