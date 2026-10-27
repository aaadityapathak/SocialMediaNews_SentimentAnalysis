"""Offline regression coverage for importing legacy GDELT CSV backups."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from gdelt_retrieve import importer


def test_legacy_numbers_bom_and_extra_columns_use_shared_sanitizer(
    tmp_path, monkeypatch
):
    path = tmp_path / "backup.csv"
    path.write_text(
        "GlobalEventID,SourceURL,DateAdded,ActionGeo_Lat,ActionGeo_Long,AvgTone,unused\n"
        "123.0,https://news.test/article,2.02605180045E+13,0,0,nan,ignored\n",
        encoding="utf-8-sig",
    )
    captured = []

    def bulk(client, actions, **kwargs):
        for action in actions:
            captured.append(action)
            yield True, {}

    monkeypatch.setattr("gdelt_retrieve.schemas.helpers.streaming_bulk", bulk)
    assert (
        importer.import_backup(
            path, index_name="selected-index", es_client=object()
        )
        == 1
    )
    action = captured[0]
    assert action["_index"] == "selected-index"
    assert action["_id"] == "123_https://news.test/article"
    assert action["_source"]["DateAdded"] == "20260518004500"
    assert action["_source"]["ActionGeo_Location"] == "0.0,0.0"
    assert action["_source"]["AvgTone"] is None
    assert "unused" not in action["_source"]


def test_csv_batches_are_consumed_only_as_each_upload_finishes(monkeypatch):
    consumed = []
    uploads = []

    def rows(path):
        for number in range(5):
            consumed.append(number)
            yield {"GlobalEventID": str(number), "SourceURL": "url"}

    monkeypatch.setattr(importer, "iter_backup_rows", rows)

    def upload(client, batch, index):
        uploads.append(len(batch))
        assert len(consumed) == sum(uploads)
        return len(batch)

    monkeypatch.setattr(importer, "upload_to_elasticsearch", upload)
    assert (
        importer.import_backup(
            "unused.csv", index_name="target", batch_size=2, es_client=object()
        )
        == 5
    )
    assert uploads == [2, 2, 1]


def test_partial_bulk_failure_stops_reading_and_closes_owned_resources(
    monkeypatch,
):
    consumed = []
    closed = []

    def rows(path):
        try:
            for number in range(5):
                consumed.append(number)
                yield {"GlobalEventID": str(number), "SourceURL": "url"}
        finally:
            closed.append(True)

    client = MagicMock()
    monkeypatch.setattr(importer, "iter_backup_rows", rows)
    monkeypatch.setattr(
        importer,
        "ESSettings",
        lambda: SimpleNamespace(host="https://example.test", api_key="test"),
    )
    monkeypatch.setattr(importer, "Elasticsearch", lambda *a, **k: client)

    def bulk(client, actions, **kwargs):
        for index, action in enumerate(actions):
            yield index == 0, {}

    monkeypatch.setattr("gdelt_retrieve.schemas.helpers.streaming_bulk", bulk)
    with pytest.raises(RuntimeError, match="1 documents"):
        importer.import_backup("unused.csv", index_name="target", batch_size=2)
    assert consumed == [0, 1]
    assert closed == [True]
    client.__exit__.assert_called_once()


@pytest.mark.parametrize(
    "content",
    [
        "GlobalEventID,DateAdded\n1,20260101\n",
        "GlobalEventID,SourceURL\n,https://news.test\n",
        "GlobalEventID,SourceURL,DateAdded\n1,https://news.test,20261301\n",
    ],
)
def test_malformed_csv_fails_before_connecting(tmp_path, monkeypatch, content):
    path = tmp_path / "invalid.csv"
    path.write_text(content, encoding="utf-8")
    factory = MagicMock()
    monkeypatch.setattr(importer, "Elasticsearch", factory)
    with pytest.raises(ValueError):
        importer.import_backup(path, index_name="target")
    factory.assert_not_called()


def test_cli_passes_explicit_file_index_and_batch_size(monkeypatch):
    upload = MagicMock(return_value=3)
    monkeypatch.setattr(importer, "import_backup", upload)
    monkeypatch.setattr(
        "sys.argv",
        [
            "gdelt_upload_backup.py",
            "my backup.csv",
            "--index",
            "custom-news",
            "--batch-size",
            "75",
        ],
    )
    importer.main()
    upload.assert_called_once_with(
        file_path=Path("my backup.csv"), index_name="custom-news", batch_size=75
    )
