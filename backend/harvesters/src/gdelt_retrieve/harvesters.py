from __future__ import annotations

from datetime import datetime, timedelta
from typing import Iterator

from .file_client import GdeltFileClient
from .gdelt_harvest import (
    GdeltHavestor,
    EventRecord,
    GkgRecord,
    EVENTS_SPEC,
    GKG_SPEC,
    EVENTS_15M_SPEC,
    GKG_15M_SPEC,
)

DEFAULT_COUNTRY_FIPS = "AS"
DEFAULT_ACTOR_CAMEO = "AUS"
DEFAULT_ADM1 = None


class EventsHarvester(GdeltHavestor[EventRecord]):
    COLUMN_HEADERS = [
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
        country_fips = kwargs.get("country_fips", DEFAULT_COUNTRY_FIPS)
        adm1_code = kwargs.get("adm1_code", DEFAULT_ADM1)
        actor_cameo = kwargs.get("actor_cameo", DEFAULT_ACTOR_CAMEO)
        skip_existing = kwargs.get("skip_existing", False)

        client = GdeltFileClient(self.raw_dir)

        # Interval logic setup
        current = start_date
        spec = EVENTS_15M_SPEC if interval == "15m" else EVENTS_SPEC
        delta = (
            timedelta(minutes=15) if interval == "15m" else timedelta(days=1)
        )

        while current <= end_date:
            # 15m mode uses precise timestamps; Daily mode uses just the date
            date_str = (
                current.strftime("%Y%m%d%H%M00")
                if interval == "15m"
                else current.strftime("%Y%m%d")
            )
            self.logger.info(f"[events] Processing: {date_str}")

            zip_path, ok = client.ensure_downloaded(
                spec, date_str, skip_existing=skip_existing
            )
            if not ok:
                self.logger.warning(
                    f"[events] Skipping {date_str} — download failed"
                )
                current += delta
                continue

            total = passed = malformed = 0
            for raw_row in client.iter_rows(zip_path):
                total += 1

                # --- V2 SCHEMA TRANSLATION (GDELT 2.0 to 1.0) ---
                # GDELT 2.0 Events have 61 columns because they added ADM2 locations.
                # To perfectly preserve your V1 logic and classes, we strip the 3 new ADM2
                # columns in reverse order, seamlessly transforming a V2 row into a V1 row.
                if interval == "15m" and len(raw_row) >= 61:
                    del raw_row[55]  # Remove ActionGeo_ADM2Code
                    del raw_row[47]  # Remove Actor2Geo_ADM2Code
                    del raw_row[39]  # Remove Actor1Geo_ADM2Code
                elif len(raw_row) < 53:
                    malformed += 1
                    continue

                # --- OPTIMIZATION A: Raw Index Pre-filtering ---
                if country_fips:
                    if not (
                        raw_row[51] == country_fips
                        or raw_row[37] == country_fips
                        or raw_row[44] == country_fips
                    ):
                        continue
                if adm1_code:
                    if not (
                        raw_row[52] == adm1_code
                        or raw_row[38] == adm1_code
                        or raw_row[45] == adm1_code
                    ):
                        continue
                if actor_cameo:
                    if not (
                        raw_row[7] == actor_cameo or raw_row[17] == actor_cameo
                    ):
                        continue

                record = EventRecord.from_row(raw_row)
                passed += 1
                yield record

            self.logger.info(
                f"[events] {date_str}: total={total:,}  matched={passed:,}  malformed={malformed}"
            )

            # --- CLEANUP LOGIC ---
            if delete_raw and zip_path.exists():
                zip_path.unlink()
                self.logger.info(f"[events] Deleted raw file: {zip_path.name}")

            current += delta


class GkgHarvester(GdeltHavestor[GkgRecord]):
    COLUMN_HEADERS = [
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
        country_fips = kwargs.get("country_fips", DEFAULT_COUNTRY_FIPS)
        adm1_code = kwargs.get("adm1_code", DEFAULT_ADM1)
        skip_existing = kwargs.get("skip_existing", False)

        client = GdeltFileClient(self.raw_dir)

        current = start_date
        spec = GKG_15M_SPEC if interval == "15m" else GKG_SPEC
        delta = (
            timedelta(minutes=15) if interval == "15m" else timedelta(days=1)
        )

        while current <= end_date:
            date_str = (
                current.strftime("%Y%m%d%H%M00")
                if interval == "15m"
                else current.strftime("%Y%m%d")
            )
            self.logger.info(f"[gkg] Processing: {date_str}")

            zip_path, ok = client.ensure_downloaded(
                spec, date_str, skip_existing=skip_existing
            )
            if not ok:
                self.logger.warning(
                    f"[gkg] Skipping {date_str} — download failed"
                )
                current += delta
                continue

            total = passed = malformed = 0
            for raw_row in client.iter_rows(zip_path):
                total += 1

                # --- V2 SCHEMA TRANSLATION (GDELT 2.0 to 1.0) ---
                # GDELT 2.0 GKG has completely restructured columns (27 columns).
                # We extract the relevant V2 columns and map them precisely to the V1 positions.
                if interval == "15m":
                    if len(raw_row) >= 26:
                        raw_row = [
                            raw_row[1],  # 0: V2 DATE
                            "1",  # 1: NUMARTS (Deprecated in V2, defaulted to 1)
                            raw_row[5],  # 2: COUNTS
                            raw_row[7],  # 3: THEMES
                            raw_row[9],  # 4: LOCATIONS
                            raw_row[11],  # 5: PERSONS
                            raw_row[13],  # 6: ORGANIZATIONS
                            raw_row[15],  # 7: TONE
                            "",  # 8: CAMEOEVENTIDS (Not mapped natively in V2)
                            raw_row[3],  # 9: SOURCES
                            raw_row[4],  # 10: SOURCEURLS
                        ]
                    else:
                        malformed += 1
                        continue
                elif len(raw_row) <= 4:
                    malformed += 1
                    continue

                # --- OPTIMIZATION A: Raw Index Pre-filtering ---
                locations_str = raw_row[4]
                if not locations_str.strip():
                    continue

                if country_fips or adm1_code:
                    blocks = [
                        b.split("#")
                        for b in locations_str.split(";")
                        if b.strip()
                    ]

                    if country_fips:
                        if not any(
                            len(b) > 2 and b[2] == country_fips for b in blocks
                        ):
                            continue

                    if adm1_code:
                        if not any(
                            len(b) > 3 and b[3] == adm1_code for b in blocks
                        ):
                            continue

                record = GkgRecord.from_row(raw_row)
                passed += 1
                yield record

            self.logger.info(
                f"[gkg] {date_str}: total={total:,}  matched={passed:,}  malformed={malformed}"
            )

            # --- CLEANUP LOGIC ---
            if delete_raw and zip_path.exists():
                zip_path.unlink()
                self.logger.info(f"[gkg] Deleted raw file: {zip_path.name}")

            current += delta
