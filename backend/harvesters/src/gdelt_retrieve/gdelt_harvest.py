from __future__ import annotations

import logging
import sys
from abc import ABC, abstractmethod
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import datetime
from typing import TypeVar

DataPoint = TypeVar("DataPoint")


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    return logger


@dataclass(frozen=True, slots=True)
class GdeltFileSpec:
    """Configuration specification for a specific GDELT file type."""

    label: str
    url_template: str
    filename_template: str

    def url(self, date_str: str) -> str:
        return self.url_template.format(date=date_str)

    def filename(self, date_str: str) -> str:
        return self.filename_template.format(date=date_str)


# Daily Specs
EVENTS_SPEC = GdeltFileSpec(
    label="events_daily",
    url_template="http://data.gdeltproject.org/events/{date}.export.CSV.zip",
    filename_template="{date}.export.CSV.zip",
)

GKG_SPEC = GdeltFileSpec(
    label="gkg_daily",
    url_template="http://data.gdeltproject.org/gkg/{date}.gkg.csv.zip",
    filename_template="{date}.gkg.csv.zip",
)

# 15-Minute Specs
EVENTS_15M_SPEC = GdeltFileSpec(
    label="events_15m",
    url_template="http://data.gdeltproject.org/gdeltv2/{date}.export.CSV.zip",
    filename_template="{date}.export.CSV.zip",
)

GKG_15M_SPEC = GdeltFileSpec(
    label="gkg_15m",
    url_template="http://data.gdeltproject.org/gdeltv2/{date}.gkg.csv.zip",
    filename_template="{date}.gkg.csv.zip",
)


@dataclass(slots=True)
class EventRecord:
    """Data container representing a single row in the GDELT v1.0 Events dataset."""

    GlobalEventID: str
    Day: str
    Actor1Code: str
    Actor1Name: str
    Actor1CountryCode: str
    Actor1KnownGroupCode: str
    Actor1EthnicCode: str
    Actor1Religion1Code: str
    Actor1Religion2Code: str
    Actor1Type1Code: str
    Actor1Type2Code: str
    Actor1Type3Code: str
    Actor2Code: str
    Actor2Name: str
    Actor2CountryCode: str
    Actor2KnownGroupCode: str
    Actor2EthnicCode: str
    Actor2Religion1Code: str
    Actor2Religion2Code: str
    Actor2Type1Code: str
    Actor2Type2Code: str
    Actor2Type3Code: str
    IsRootEvent: str
    EventCode: str
    EventBaseCode: str
    EventRootCode: str
    QuadClass: str
    GoldsteinScale: str
    NumMentions: str
    NumSources: str
    NumArticles: str
    AvgTone: str
    Actor1Geo_Type: str
    Actor1Geo_Fullname: str
    Actor1Geo_CountryCode: str
    Actor1Geo_ADM1Code: str
    Actor1Geo_Lat: str
    Actor1Geo_Long: str
    Actor1Geo_FeatureID: str
    Actor2Geo_Type: str
    Actor2Geo_Fullname: str
    Actor2Geo_CountryCode: str
    Actor2Geo_ADM1Code: str
    Actor2Geo_Lat: str
    Actor2Geo_Long: str
    Actor2Geo_FeatureID: str
    ActionGeo_Type: str
    ActionGeo_Fullname: str
    ActionGeo_CountryCode: str
    ActionGeo_ADM1Code: str
    ActionGeo_Lat: str
    ActionGeo_Long: str
    ActionGeo_FeatureID: str
    DateAdded: str
    SourceURL: str
    extra: list[str] = field(default_factory=list, repr=False)

    @classmethod
    def from_row(cls, row: list[str]) -> EventRecord:
        r = row + [""] * max(0, 58 - len(row))
        return cls(
            GlobalEventID=r[0],
            Day=r[1],
            Actor1Code=r[5],
            Actor1Name=r[6],
            Actor1CountryCode=r[7],
            Actor1KnownGroupCode=r[8],
            Actor1EthnicCode=r[9],
            Actor1Religion1Code=r[10],
            Actor1Religion2Code=r[11],
            Actor1Type1Code=r[12],
            Actor1Type2Code=r[13],
            Actor1Type3Code=r[14],
            Actor2Code=r[15],
            Actor2Name=r[16],
            Actor2CountryCode=r[17],
            Actor2KnownGroupCode=r[18],
            Actor2EthnicCode=r[19],
            Actor2Religion1Code=r[20],
            Actor2Religion2Code=r[21],
            Actor2Type1Code=r[22],
            Actor2Type2Code=r[23],
            Actor2Type3Code=r[24],
            IsRootEvent=r[25],
            EventCode=r[26],
            EventBaseCode=r[27],
            EventRootCode=r[28],
            QuadClass=r[29],
            GoldsteinScale=r[30],
            NumMentions=r[31],
            NumSources=r[32],
            NumArticles=r[33],
            AvgTone=r[34],
            Actor1Geo_Type=r[35],
            Actor1Geo_Fullname=r[36],
            Actor1Geo_CountryCode=r[37],
            Actor1Geo_ADM1Code=r[38],
            Actor1Geo_Lat=r[39],
            Actor1Geo_Long=r[40],
            Actor1Geo_FeatureID=r[41],
            Actor2Geo_Type=r[42],
            Actor2Geo_Fullname=r[43],
            Actor2Geo_CountryCode=r[44],
            Actor2Geo_ADM1Code=r[45],
            Actor2Geo_Lat=r[46],
            Actor2Geo_Long=r[47],
            Actor2Geo_FeatureID=r[48],
            ActionGeo_Type=r[49],
            ActionGeo_Fullname=r[50],
            ActionGeo_CountryCode=r[51],
            ActionGeo_ADM1Code=r[52],
            ActionGeo_Lat=r[53],
            ActionGeo_Long=r[54],
            ActionGeo_FeatureID=r[55],
            DateAdded=r[56],
            SourceURL=r[57],
            extra=row[58:],
        )

    def to_row(self) -> list[str]:
        return [
            self.GlobalEventID,
            self.Day,
            "",
            "",
            "",
            self.Actor1Code,
            self.Actor1Name,
            self.Actor1CountryCode,
            self.Actor1KnownGroupCode,
            self.Actor1EthnicCode,
            self.Actor1Religion1Code,
            self.Actor1Religion2Code,
            self.Actor1Type1Code,
            self.Actor1Type2Code,
            self.Actor1Type3Code,
            self.Actor2Code,
            self.Actor2Name,
            self.Actor2CountryCode,
            self.Actor2KnownGroupCode,
            self.Actor2EthnicCode,
            self.Actor2Religion1Code,
            self.Actor2Religion2Code,
            self.Actor2Type1Code,
            self.Actor2Type2Code,
            self.Actor2Type3Code,
            self.IsRootEvent,
            self.EventCode,
            self.EventBaseCode,
            self.EventRootCode,
            self.QuadClass,
            self.GoldsteinScale,
            self.NumMentions,
            self.NumSources,
            self.NumArticles,
            self.AvgTone,
            self.Actor1Geo_Type,
            self.Actor1Geo_Fullname,
            self.Actor1Geo_CountryCode,
            self.Actor1Geo_ADM1Code,
            self.Actor1Geo_Lat,
            self.Actor1Geo_Long,
            self.Actor1Geo_FeatureID,
            self.Actor2Geo_Type,
            self.Actor2Geo_Fullname,
            self.Actor2Geo_CountryCode,
            self.Actor2Geo_ADM1Code,
            self.Actor2Geo_Lat,
            self.Actor2Geo_Long,
            self.Actor2Geo_FeatureID,
            self.ActionGeo_Type,
            self.ActionGeo_Fullname,
            self.ActionGeo_CountryCode,
            self.ActionGeo_ADM1Code,
            self.ActionGeo_Lat,
            self.ActionGeo_Long,
            self.ActionGeo_FeatureID,
            self.DateAdded,
            self.SourceURL,
        ] + self.extra


@dataclass(slots=True)
class GkgRecord:
    """Data container representing a single row in the GDELT v1.0 GKG dataset."""

    DATE: str
    NUMARTS: str
    COUNTS: str
    THEMES: str
    LOCATIONS: str
    PERSONS: str
    ORGANIZATIONS: str
    TONE: str
    CAMEOEVENTIDS: str
    SOURCES: str
    SOURCEURLS: str
    extra: list[str] = field(default_factory=list, repr=False)

    @classmethod
    def from_row(cls, row: list[str]) -> GkgRecord:
        r = row + [""] * max(0, 11 - len(row))
        return cls(
            DATE=r[0],
            NUMARTS=r[1],
            COUNTS=r[2],
            THEMES=r[3],
            LOCATIONS=r[4],
            PERSONS=r[5],
            ORGANIZATIONS=r[6],
            TONE=r[7],
            CAMEOEVENTIDS=r[8],
            SOURCES=r[9],
            SOURCEURLS=r[10],
            extra=row[11:],
        )

    def location_blocks(self) -> list[list[str]]:
        if not self.LOCATIONS.strip():
            return []
        return [b.split("#") for b in self.LOCATIONS.split(";") if b.strip()]

    def themes_list(self) -> list[str]:
        return [t for t in self.THEMES.split(";") if t]

    def to_row(self) -> list[str]:
        return [
            self.DATE,
            self.NUMARTS,
            self.COUNTS,
            self.THEMES,
            self.LOCATIONS,
            self.PERSONS,
            self.ORGANIZATIONS,
            self.TONE,
            self.CAMEOEVENTIDS,
            self.SOURCES,
            self.SOURCEURLS,
        ] + self.extra


class GdeltHavestor[DataPoint](ABC):
    """Abstract base class establishing the contract for all data harvesters."""

    def __init__(self, raw_dir: str | None = None) -> None:
        from pathlib import Path

        self.raw_dir: Path = Path(raw_dir) if raw_dir else Path("data/raw")
        self.logger = get_logger(f"gdelt.{self.__class__.__name__}")

    @abstractmethod
    def run(
        self,
        start_date: datetime,
        end_date: datetime,
        interval: str = "daily",
        delete_raw: bool = False,
        **kwargs,
    ) -> Iterator[DataPoint]:
        """
        Parameters
        ----------
        interval: str
            "daily" for GDELT 1.0 (1 file per day) or "15m" for GDELT 2.0 (1 file per 15 mins).
        delete_raw: bool
            If True, instantly unlinks the downloaded raw ZIP file from the disk after yielding rows.
        """
        raise NotImplementedError
