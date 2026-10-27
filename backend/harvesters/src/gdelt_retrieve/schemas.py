import hashlib
import logging
import math
from collections.abc import Iterable, Iterator
from typing import Any

from elastic.settings import ESSettings
from elasticsearch import Elasticsearch, helpers

logger = logging.getLogger(__name__)

# --- CENTRALIZED COLUMN CONFIGURATION ---
USEFUL_COLUMNS = [
    "GlobalEventID",
    "Day",
    "DateAdded",
    "SourceURL",
    "Actor1Name",
    "Actor1CountryCode",
    "Actor2Name",
    "Actor2CountryCode",
    "EventCode",
    "EventRootCode",
    "QuadClass",
    "ActionGeo_Fullname",
    "ActionGeo_Lat",
    "ActionGeo_Long",
    "ActionGeo_CountryCode",
    "GoldsteinScale",
    "NumMentions",
    "NumSources",
    "NumArticles",
    "AvgTone",
    "GKG_THEMES",
    "GKG_PERSONS",
    "GKG_ORGANIZATIONS",
    "GKG_TONE",
]

FLOAT_FIELDS = [
    "FractionDate",
    "GoldsteinScale",
    "AvgTone",
    "Actor1Geo_Lat",
    "Actor1Geo_Long",
    "Actor2Geo_Lat",
    "Actor2Geo_Long",
    "ActionGeo_Lat",
    "ActionGeo_Long",
]

INT_FIELDS = [
    "Day",
    "MonthYear",
    "Year",
    "IsRootEvent",
    "QuadClass",
    "NumMentions",
    "NumSources",
    "NumArticles",
    "Actor1Geo_Type",
    "Actor2Geo_Type",
    "ActionGeo_Type",
]


def generate_actions_from_memory(
    rows: Iterable[dict[str, Any]], index_name: str
) -> Iterator[dict[str, Any]]:
    for row in rows:
        sanitized_row = {}

        # Sanitization
        for key, value in row.items():
            if value is None or str(value).strip() == "":
                sanitized_row[key] = None
            elif key in FLOAT_FIELDS:
                try:
                    number = float(value)
                    sanitized_row[key] = (
                        number if math.isfinite(number) else None
                    )
                except (ValueError, TypeError, OverflowError):
                    sanitized_row[key] = None
            elif key in INT_FIELDS:
                try:
                    sanitized_row[key] = int(value)
                except (ValueError, TypeError, OverflowError):
                    sanitized_row[key] = None
            else:
                sanitized_row[key] = str(value).strip()

        # Parse tone components independently; a bad component must not lose
        # valid siblings or emit non-finite values rejected by Elasticsearch.
        tone = sanitized_row.pop("GKG_TONE", None)
        if tone:
            names = ("Score", "Positive", "Negative", "Polarity")
            for name, value in zip(names, tone.split(",")):
                try:
                    number = float(value)
                    number = number if math.isfinite(number) else None
                except (ValueError, TypeError):
                    number = None
                sanitized_row[f"GKG_Tone_{name}"] = number

        # Array Formatting (Listification)
        for arr_field in ["GKG_THEMES", "GKG_PERSONS", "GKG_ORGANIZATIONS"]:
            if sanitized_row.get(arr_field):
                sanitized_row[arr_field] = [
                    x.strip()
                    for x in sanitized_row[arr_field].split(";")
                    if x.strip()
                ]

        # Geo-spatial mapping
        if (
            sanitized_row.get("Actor1Geo_Lat") is not None
            and sanitized_row.get("Actor1Geo_Long") is not None
        ):
            sanitized_row["Actor1Geo_Location"] = (
                f"{sanitized_row['Actor1Geo_Lat']},{sanitized_row['Actor1Geo_Long']}"
            )

        if (
            sanitized_row.get("Actor2Geo_Lat") is not None
            and sanitized_row.get("Actor2Geo_Long") is not None
        ):
            sanitized_row["Actor2Geo_Location"] = (
                f"{sanitized_row['Actor2Geo_Lat']},{sanitized_row['Actor2Geo_Long']}"
            )

        if (
            sanitized_row.get("ActionGeo_Lat") is not None
            and sanitized_row.get("ActionGeo_Long") is not None
        ):
            sanitized_row["ActionGeo_Location"] = (
                f"{sanitized_row['ActionGeo_Lat']},{sanitized_row['ActionGeo_Long']}"
            )

        document_id = f"{sanitized_row.get('GlobalEventID', 'UKN')}_{sanitized_row.get('SourceURL', 'UKN')}"
        if len(document_id.encode("utf-8")) > 512:
            document_id = hashlib.sha256(
                document_id.encode("utf-8")
            ).hexdigest()
        yield {
            "_index": index_name,
            "_id": document_id,
            "_source": sanitized_row,
        }


def upload_to_elasticsearch_local(
    rows: Iterable[dict[str, Any]], index_name: str = "gdelt-index"
):
    settings = ESSettings()
    with Elasticsearch(
        settings.host,
        api_key=settings.api_key,
        verify_certs=False,
    ) as client:
        return upload_to_elasticsearch(client, rows, index_name)


def upload_to_elasticsearch(
    client: Elasticsearch,
    rows: Iterable[dict[str, Any]],
    index_name: str = "gdelt-index",
) -> int:
    # streaming_bulk bounds memory and retries rejected chunks. Surface final
    # failures so schedulers do not advance past a partially ingested batch.
    success = failures = 0
    for ok, _ in helpers.streaming_bulk(
        client,
        generate_actions_from_memory(rows, index_name),
        chunk_size=500,
        max_retries=3,
        initial_backoff=1,
        max_backoff=8,
        raise_on_error=False,
    ):
        if ok:
            success += 1
        else:
            failures += 1
    if failures:
        raise RuntimeError(f"GDELT indexing failed for {failures} documents")
    logger.info("Indexed %s GDELT documents", success)
    return success
