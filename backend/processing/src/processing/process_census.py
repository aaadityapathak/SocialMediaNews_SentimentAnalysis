import logging
from pathlib import Path
from shapely.geometry import mapping

log = logging.getLogger(__name__)

CENSUS_INDEX = "census-travel-zones"
CENSUS_QUEUE = "census:queue"

# Last field per occupation-group prefix = total for that mode (ABS convention)
LGA_MODE_PREFIXES = {
    "train": "m1_train_",
    "bus": "m1_bus_",
    "ferry": "m1_ferry_",
    "tram": "m1_tram_",
    "taxi": "m1_taxi_",
    "car_driver": "m1_carasd",
    "car_passenger": "m1_carasp",
    "truck": "m1_truck_",
    "motorbike": "m1_mbikes",
    "bicycle": "m1_bicycl",
    "walk_only": "m1_wlkonl",
    "other": "m1_oth_",
}
LGA_TOTAL_PREFIX = "m1_tot_m1"

SA2_MODE_PREFIXES = {
    "train": "f_m1_train",
    "bus": "f_m1_bus_",
    "ferry": "f_m1_ferr",
    "tram": "f_m1_tram",
    "taxi": "f_m1_taxi",
    "car": "f_m1_car",
    "truck": "f_m1_truc",
    "motorbike": "f_m1_mbik",
    "bicycle": "f_m1_bicy",
    "walk_only": "f_m1_wlko",
    "other": "f_m1_othe",
}
SA2_TOTAL_PREFIX = "f_m1_tot_"


def _last_field(columns: list[str], prefix: str) -> str | None:
    matches = [c for c in columns if c.startswith(prefix)]
    return matches[-1] if matches else None


def _int(val) -> int:
    try:
        return int(float(val)) if val is not None else 0
    except (ValueError, TypeError):
        return 0


def _doc_id(year: int, zone_type: str, zone_code: str) -> str:
    return f"{year}_{zone_type}_{zone_code}"


def detect_dataset(shp_path: Path) -> tuple[str, int] | None:
    name = shp_path.stem.lower()
    if "lga" in name and "2021" in name:
        return "lga", 2021
    if "sa2" in name and "2016" in name:
        return "sa2", 2016
    log.warning("Unknown dataset: %s", shp_path.name)
    return None


def extract_record(row, columns: list[str], zone_type: str, year: int) -> dict:
    if zone_type == "lga":
        mode_prefixes = LGA_MODE_PREFIXES
        total_prefix = LGA_TOTAL_PREFIX
        zone_code = str(row.get("lga_code22") or row.get("lga_code_2", ""))
        zone_name = str(row.get("lga_name22", ""))
        state = str(row.get("ste_name21", ""))
    else:
        mode_prefixes = SA2_MODE_PREFIXES
        total_prefix = SA2_TOTAL_PREFIX
        zone_code = str(row.get("sa2_main16", ""))
        zone_name = str(row.get("sa2_name16", ""))
        state = str(row.get("ste_name16", ""))

    modes = {}
    for mode, prefix in mode_prefixes.items():
        field = _last_field(columns, prefix)
        modes[mode] = _int(row.get(field)) if field else 0

    total_field = _last_field(columns, total_prefix)
    modes["total"] = (
        _int(row.get(total_field)) if total_field else sum(modes.values())
    )

    countable = {k: v for k, v in modes.items() if k != "total" and v > 0}
    dominant = max(countable, key=countable.get) if countable else "other"

    geom = mapping(row["geometry"]) if row.get("geometry") is not None else None

    return {
        "_id": _doc_id(year, zone_type, zone_code),
        "zone_code": zone_code,
        "zone_name": zone_name,
        "zone_type": zone_type,
        "state": state,
        "year": year,
        "travel_modes": modes,
        "dominant_mode": dominant,
        "geometry": geom,
    }
