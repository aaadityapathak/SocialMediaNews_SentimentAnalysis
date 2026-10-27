"""
gdelt_retrieve
==============
GDELT v1.0 and v2.0 (15-min) data harvesting package.

This module exposes the public API for the GDELT retrieval system,
hiding internal file implementations from the consumer.
"""

from .filters import (
    event_is_australia,
    event_is_victoria,
    event_matches,
    gkg_is_australia,
    gkg_is_victoria,
    gkg_matches,
)
from .gdelt_harvest import EVENTS_15M_SPEC as EVENTS_15M_SPEC
from .gdelt_harvest import EVENTS_SPEC as EVENTS_SPEC
from .gdelt_harvest import GKG_15M_SPEC as GKG_15M_SPEC
from .gdelt_harvest import GKG_SPEC as GKG_SPEC
from .gdelt_harvest import DataPoint as DataPoint
from .gdelt_harvest import EventRecord as EventRecord
from .gdelt_harvest import GdeltHavestor as GdeltHavestor
from .gdelt_harvest import GkgRecord as GkgRecord
from .harvesters import EventsHarvester as EventsHarvester
from .harvesters import GkgHarvester as GkgHarvester

__all__ = [
    "EVENTS_15M_SPEC",
    "EVENTS_SPEC",
    "GKG_15M_SPEC",
    "GKG_SPEC",
    "DataPoint",
    "EventRecord",
    "EventsHarvester",
    "GdeltHavestor",
    "GkgHarvester",
    "GkgRecord",
    "event_is_australia",
    "event_is_victoria",
    "event_matches",
    "gkg_is_australia",
    "gkg_is_victoria",
    "gkg_matches",
]
