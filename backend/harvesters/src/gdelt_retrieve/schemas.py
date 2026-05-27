import logging
from typing import Iterator, Dict, Any
from elasticsearch import Elasticsearch, helpers
from elastic.settings import ESSettings

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
    rows: list[Dict[str, Any]], index_name: str
) -> Iterator[Dict[str, Any]]:
    for row in rows:
        sanitized_row = {}

        # Sanitization
        for key, value in row.items():
            if value is None or str(value).strip() == "":
                sanitized_row[key] = None
            elif key in FLOAT_FIELDS:
                try:
                    sanitized_row[key] = float(value)
                except ValueError:
                    sanitized_row[key] = None
            elif key in INT_FIELDS:
                try:
                    sanitized_row[key] = int(value)
                except ValueError:
                    sanitized_row[key] = None
            else:
                sanitized_row[key] = str(value).strip()

        # Extract & Rename GKG Tone Values
        if sanitized_row.get("GKG_TONE"):
            tone_parts = sanitized_row["GKG_TONE"].split(",")
            if len(tone_parts) >= 4:
                try:
                    sanitized_row["GKG_Tone_Score"] = (
                        float(tone_parts[0]) if tone_parts[0] else None
                    )
                    sanitized_row["GKG_Tone_Positive"] = (
                        float(tone_parts[1]) if tone_parts[1] else None
                    )
                    sanitized_row["GKG_Tone_Negative"] = (
                        float(tone_parts[2]) if tone_parts[2] else None
                    )
                    sanitized_row["GKG_Tone_Polarity"] = (
                        float(tone_parts[3]) if tone_parts[3] else None
                    )
                except ValueError:
                    pass
            del sanitized_row["GKG_TONE"]

        # Array Formatting (Listification)
        for arr_field in ["GKG_THEMES", "GKG_PERSONS", "GKG_ORGANIZATIONS"]:
            if sanitized_row.get(arr_field):
                sanitized_row[arr_field] = [
                    x.strip()
                    for x in sanitized_row[arr_field].split(";")
                    if x.strip()
                ]

        # Geo-spatial mapping
        if sanitized_row.get("Actor1Geo_Lat") and sanitized_row.get(
            "Actor1Geo_Long"
        ):
            sanitized_row["Actor1Geo_Location"] = (
                f"{sanitized_row['Actor1Geo_Lat']},{sanitized_row['Actor1Geo_Long']}"
            )

        if sanitized_row.get("Actor2Geo_Lat") and sanitized_row.get(
            "Actor2Geo_Long"
        ):
            sanitized_row["Actor2Geo_Location"] = (
                f"{sanitized_row['Actor2Geo_Lat']},{sanitized_row['Actor2Geo_Long']}"
            )

        if sanitized_row.get("ActionGeo_Lat") and sanitized_row.get(
            "ActionGeo_Long"
        ):
            sanitized_row["ActionGeo_Location"] = (
                f"{sanitized_row['ActionGeo_Lat']},{sanitized_row['ActionGeo_Long']}"
            )

        yield {
            "_index": index_name,
            "_id": f"{sanitized_row.get('GlobalEventID', 'UKN')}_{sanitized_row.get('SourceURL', 'UKN')}",
            "_source": sanitized_row,
        }


def upload_to_elasticsearch_local(
    rows: list[Dict[str, Any]], index_name: str = "gdelt-index"
):
    settings = ESSettings()
    client = Elasticsearch(
        settings.host,
        api_key=settings.api_key,
        verify_certs=False,
    )

    logger.info(
        f"Pushing {len(rows)} cleaned documents to ES Index: '{index_name}'"
    )
    success, failed = helpers.bulk(
        client,
        generate_actions_from_memory(rows, index_name),
        chunk_size=2000,
        raise_on_error=False,
    )

    logger.info(
        f"Upload complete. Success: {success}, Failed: {len(failed) if isinstance(failed, list) else failed}"
    )
    if failed:
        logger.warning(f"Failed Sample: {failed[:2]}")

    return success


def upload_to_elasticsearch(
    client: Elasticsearch,
    rows: list[Dict[str, Any]],
    index_name: str = "gdelt-index",
) -> int:
    logger.info(
        f"Pushing {len(rows)} cleaned documents to ES Index: '{index_name}'"
    )

    success, failed = helpers.bulk(
        client,
        generate_actions_from_memory(rows, index_name),
        chunk_size=500,
        raise_on_error=False,
    )

    logger.info(
        f"Upload complete. Success: {success}, Failed: {len(failed) if isinstance(failed, list) else failed}"
    )

    if failed:
        logger.warning(f"Failed Sample: {failed[:2]}")

    return success if success else 0
