import json
from unittest.mock import MagicMock

import pytest
from processing import census_io
from processing.indexer import Indexer
from processing.ml_client import MLServerClient, MLServerSettings
from processing.process_census import _dataset_fields, extract_record
from processing.schemas import MastodonRecord
from shapely.geometry import Point


def test_redelivery_skips_normalization_and_ml():
    es, vk, processor = MagicMock(), MagicMock(), MagicMock()
    vk.exists.return_value = 1
    indexer = Indexer(vk, es, {"mastodon": processor})
    indexer.insert(MastodonRecord(data={"uri": "post"}))
    es.index.assert_not_called()
    processor.process_record.assert_not_called()
    processor.to_common_schema.assert_not_called()
    processor.enrich_with_sentiment.assert_not_called()
    processor.enrich_with_emotion_detection.assert_not_called()


def test_partial_delivery_repairs_only_missing_common_index():
    es, vk, processor = MagicMock(), MagicMock(), MagicMock()
    vk.exists.side_effect = [1, 0]
    processor.get_record_id.return_value = "post"
    processor.build_common_id.return_value = "mastodon-post"
    processor.enrich_with_emotion_detection.return_value = {"text": "hello"}
    Indexer(vk, es, {"mastodon": processor}).insert(MastodonRecord(data={}))
    processor.process_record.assert_not_called()
    processor.enrich_with_sentiment.assert_called_once()
    es.index.assert_called_once_with(
        index="social-posts-index",
        id="mastodon-post",
        document={"text": "hello"},
    )
    assert vk.exists.call_count == 2
    vk.set.assert_called_once()


def test_failed_write_does_not_mark_record_processed():
    es, vk = MagicMock(), MagicMock()
    es.index.side_effect = RuntimeError("offline")
    vk.exists.return_value = 0
    with pytest.raises(RuntimeError, match="offline"):
        Indexer(vk, es, {}).insert_to_index("posts", {}, "id")
    vk.set.assert_not_called()


def test_ml_client_timeout_override_and_cleanup(monkeypatch):
    session = MagicMock()
    session.post.return_value.json.return_value = {"sentiment": {"positive": 1}}
    monkeypatch.setattr(
        "processing.ml_client.requests.Session", lambda: session
    )
    with MLServerClient(
        MLServerSettings(api_key="test"), request_timeout=2
    ) as client:
        assert client.sentiment_analysis("hello") == {"positive": 1}
    assert session.post.call_args.kwargs["timeout"] == 2
    session.close.assert_called_once()


def test_census_field_resolution_and_nonfinite_values():
    row = {
        "lga_code22": "1",
        "lga_name22": "Test",
        "m1_train_1": 99,
        "m1_train_total": 5,
        "m1_bus_total": float("inf"),
        "geometry": Point(144, -37),
    }
    _dataset_fields.cache_clear()
    first = extract_record(row, list(row), "lga", 2021)
    extract_record(row, list(row), "lga", 2021)
    assert first["travel_modes"]["train"] == 5
    assert first["travel_modes"]["bus"] == 0
    assert first["dominant_mode"] == "train"
    assert first["_id"] == "2021_lga_1"
    assert _dataset_fields.cache_info().hits == 1


def test_census_queue_batches_preserve_order():
    vk = MagicMock()
    records = [{"_id": str(i)} for i in range(5)]
    assert census_io.enqueue_records(vk, iter(records), batch_size=2) == 5
    calls = vk.rpush.call_args_list
    assert [len(call.args) - 1 for call in calls] == [2, 2, 1]
    assert [
        json.loads(payload) for call in calls for payload in call.args[1:]
    ] == records


def test_census_bulk_upsert_is_idempotent_and_does_not_mutate(monkeypatch):
    record = {"_id": "2021_lga_1", "zone_name": "Test"}

    def bulk(es, actions, **kwargs):
        assert kwargs["chunk_size"] == 10
        assert kwargs["max_retries"] == 3
        assert list(actions) == [
            {
                "_op_type": "update",
                "_index": "census-travel-zones",
                "_id": "2021_lga_1",
                "doc": {"zone_name": "Test"},
                "doc_as_upsert": True,
            }
        ]
        yield True, {}

    monkeypatch.setattr(census_io, "streaming_bulk", bulk)
    assert census_io.bulk_upsert(MagicMock(), [record], 10) == 1
    assert record["_id"] == "2021_lga_1"


def test_census_bulk_failure_is_not_success(monkeypatch):
    monkeypatch.setattr(
        census_io,
        "streaming_bulk",
        lambda *a, **k: iter([(False, {"error": "bad"})]),
    )
    with pytest.raises(RuntimeError, match="bulk write failed"):
        census_io.bulk_upsert(MagicMock(), [{"_id": "id"}])


def test_census_reads_root_and_subfolder(tmp_path):
    (tmp_path / "lga2021.shp").touch()
    (tmp_path / "nested").mkdir()
    (tmp_path / "nested" / "sa22016.shp").touch()
    assert len(list(census_io.iter_shapefiles(str(tmp_path)))) == 2


def test_census_reads_real_geometry_and_projects_to_wgs84(tmp_path):
    import geopandas as gpd

    path = tmp_path / "lga2021.shp"
    gpd.GeoDataFrame(
        {"lga_code22": ["1"], "geometry": [Point(144, -37)]},
        crs=4326,
    ).to_file(path)
    records = list(census_io.read_records(path))
    assert len(records) == 1
    assert records[0]["geometry"]["coordinates"] == (144, -37)


def test_upload_closes_client_on_failure(monkeypatch):
    import census_upload

    vk = MagicMock()
    monkeypatch.setattr(census_upload, "Valkey", lambda **kwargs: vk)
    monkeypatch.setattr(
        census_upload, "_iter_shapefiles", lambda *args: ["file"]
    )
    monkeypatch.setattr(
        census_upload, "_read_records", lambda *args: iter([{"_id": "id"}])
    )
    vk.rpush.side_effect = RuntimeError("queue down")
    with pytest.raises(RuntimeError, match="queue down"):
        census_upload.upload()
    vk.close.assert_called_once()


def test_consumer_rejects_invalid_payload_before_connecting(monkeypatch):
    import consumer
    from flask import Flask

    connect = MagicMock()
    monkeypatch.setattr(consumer, "Elasticsearch", connect)
    with Flask(__name__).test_request_context(data='{"source":"invalid"}'):
        _, status = consumer.load_social_to_es()
    assert status == 422
    connect.assert_not_called()


def test_consumer_closes_existing_clients_if_later_client_fails(monkeypatch):
    import consumer
    from flask import Flask

    es = MagicMock()
    monkeypatch.setattr(consumer, "read_from_secret", lambda *args: MagicMock())
    monkeypatch.setattr(consumer, "Elasticsearch", lambda *args, **kwargs: es)
    monkeypatch.setattr(
        consumer, "Valkey", MagicMock(side_effect=RuntimeError("offline"))
    )
    with Flask(__name__).test_request_context(
        data='{"source":"mastodon","data":{}}'
    ):
        _, status = consumer.load_social_to_es()
    assert status == 500
    es.close.assert_called_once()


def test_youtube_video_publication_time_survives_normalization():
    from processing.process_social import YouTubeProcessor
    from processing.schemas import YTItem

    record = YTItem(
        kind="video",
        record={"video_id": "1", "published": "2026-01-01T00:00:00Z"},
    )
    assert (
        YouTubeProcessor(MagicMock()).to_common_schema(record)["created_at"]
        == "2026-01-01T00:00:00Z"
    )
