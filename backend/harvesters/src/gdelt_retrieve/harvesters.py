from __future__ import annotations

from collections.abc import Iterator
from contextlib import closing
from datetime import datetime
from typing import ClassVar

from .gdelt_harvest import (
    EVENTS_15M_SPEC,
    EVENTS_SPEC,
    GKG_15M_SPEC,
    GKG_SPEC,
    EventRecord,
    GdeltHavestor,
    GkgRecord,
)
from .reader import iter_archive_rows

DEFAULT_COUNTRY_FIPS = "AS"
DEFAULT_ACTOR_CAMEO = "AUS"
DEFAULT_ADM1 = None


class EventsHarvester(GdeltHavestor[EventRecord]):
    COLUMN_HEADERS: ClassVar[list[str]] = [
        "GlobalEventID",
        "Day",
        "MonthYear",
        "Year",
        "FractionDate",
        "Actor1Code",
        "Actor1Name",
        "Actor1CountryCode",
        "Actor1KnownGroupCode",
        "Actor1EthnicCode",
        "Actor1Religion1Code",
        "Actor1Religion2Code",
        "Actor1Type1Code",
        "Actor1Type2Code",
        "Actor1Type3Code",
        "Actor2Code",
        "Actor2Name",
        "Actor2CountryCode",
        "Actor2KnownGroupCode",
        "Actor2EthnicCode",
        "Actor2Religion1Code",
        "Actor2Religion2Code",
        "Actor2Type1Code",
        "Actor2Type2Code",
        "Actor2Type3Code",
        "IsRootEvent",
        "EventCode",
        "EventBaseCode",
        "EventRootCode",
        "QuadClass",
        "GoldsteinScale",
        "NumMentions",
        "NumSources",
        "NumArticles",
        "AvgTone",
        "Actor1Geo_Type",
        "Actor1Geo_Fullname",
        "Actor1Geo_CountryCode",
        "Actor1Geo_ADM1Code",
        "Actor1Geo_Lat",
        "Actor1Geo_Long",
        "Actor1Geo_FeatureID",
        "Actor2Geo_Type",
        "Actor2Geo_Fullname",
        "Actor2Geo_CountryCode",
        "Actor2Geo_ADM1Code",
        "Actor2Geo_Lat",
        "Actor2Geo_Long",
        "Actor2Geo_FeatureID",
        "ActionGeo_Type",
        "ActionGeo_Fullname",
        "ActionGeo_CountryCode",
        "ActionGeo_ADM1Code",
        "ActionGeo_Lat",
        "ActionGeo_Long",
        "ActionGeo_FeatureID",
        "DateAdded",
        "SourceURL",
    ]

    def run(
        self,
        start_date: datetime,
        end_date: datetime,
        interval: str = "daily",
        delete_raw: bool = False,
        **kwargs,
    ) -> Iterator[EventRecord]:
        country = kwargs.get("country_fips", DEFAULT_COUNTRY_FIPS)
        adm1 = kwargs.get("adm1_code", DEFAULT_ADM1)
        actor = kwargs.get("actor_cameo", DEFAULT_ACTOR_CAMEO)
        rows = iter_archive_rows(
            self.raw_dir,
            start_date,
            end_date,
            interval,
            EVENTS_SPEC,
            EVENTS_15M_SPEC,
            delete_raw=delete_raw,
            skip_existing=kwargs.get("skip_existing", True),
            raise_on_download_error=kwargs.get(
                "raise_on_download_error", False
            ),
        )
        with closing(rows):
            for row in rows:
                if interval == "15m":
                    if len(row) < 61:
                        continue
                    # V2 adds ADM2 between ADM1 and latitude for each actor/action.
                    row = row[:39] + row[40:47] + row[48:55] + row[56:]
                elif len(row) < 58:
                    continue
                # Filter raw columns before allocating records for global data.
                if country and not any(row[i] == country for i in (51, 37, 44)):
                    continue
                if adm1 and not any(row[i] == adm1 for i in (52, 38, 45)):
                    continue
                if actor and not any(row[i] == actor for i in (7, 17)):
                    continue
                yield EventRecord.from_row(row)


class GkgHarvester(GdeltHavestor[GkgRecord]):
    COLUMN_HEADERS: ClassVar[list[str]] = [
        "DATE",
        "NUMARTS",
        "COUNTS",
        "THEMES",
        "LOCATIONS",
        "PERSONS",
        "ORGANIZATIONS",
        "TONE",
        "CAMEOEVENTIDS",
        "SOURCES",
        "SOURCEURLS",
    ]

    def run(
        self,
        start_date: datetime,
        end_date: datetime,
        interval: str = "daily",
        delete_raw: bool = False,
        **kwargs,
    ) -> Iterator[GkgRecord]:
        country = kwargs.get("country_fips", DEFAULT_COUNTRY_FIPS)
        adm1 = kwargs.get("adm1_code", DEFAULT_ADM1)
        rows = iter_archive_rows(
            self.raw_dir,
            start_date,
            end_date,
            interval,
            GKG_SPEC,
            GKG_15M_SPEC,
            delete_raw=delete_raw,
            skip_existing=kwargs.get("skip_existing", True),
            raise_on_download_error=kwargs.get(
                "raise_on_download_error", False
            ),
        )
        with closing(rows):
            for row in rows:
                if interval == "15m":
                    if len(row) < 27:
                        continue
                    row = [
                        row[1],
                        "1",
                        row[5],
                        row[7],
                        row[9],
                        row[11],
                        row[13],
                        row[15],
                        "",
                        row[3],
                        row[4],
                    ]
                elif len(row) < 11:
                    continue
                # Split location blocks once and stop at the first match.
                if (country or adm1) and not any(
                    len(block) > 3
                    and (not country or block[2] == country)
                    and (not adm1 or block[3] == adm1)
                    for block in (item.split("#") for item in row[4].split(";"))
                ):
                    continue
                yield GkgRecord.from_row(row)
