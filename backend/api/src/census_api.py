import logging
from shapely.geometry import shape, mapping

from elasticsearch import Elasticsearch
from flask import jsonify, request

from base.read_fission_cfg import read_from_secret
from settings import ESSettings

log = logging.getLogger(__name__)

CENSUS_INDEX = "census-travel-zones"
MAX_RESULTS = 3000
DEFAULT_TOLERANCE = 0.01  # 1km approx filter


def _simplify(geom: dict, tolerance: float) -> dict:
    try:
        return mapping(shape(geom).simplify(tolerance, preserve_topology=True))
    except Exception:
        return geom


def get_census_travel():
    es_settings = read_from_secret("elastic-api-credentials", ESSettings)
    es = Elasticsearch(
        es_settings.host, api_key=es_settings.api_key, verify_certs=False
    )

    filters = []
    year = request.args.get("year", type=int)
    state = request.args.get("state", type=str)
    zone_type = request.args.get("zone_type", type=str)
    tolerance = request.args.get(
        "tolerance", default=DEFAULT_TOLERANCE, type=float
    )

    if year:
        filters.append({"term": {"year": year}})
    if state:
        filters.append({"term": {"state": state}})
    if zone_type:
        filters.append({"term": {"zone_type": zone_type}})

    query = {"bool": {"filter": filters}} if filters else {"match_all": {}}

    result = es.search(
        index=CENSUS_INDEX,
        body={
            "query": query,
            "_source": [
                "zone_code",
                "zone_name",
                "zone_type",
                "state",
                "year",
                "travel_modes",
                "dominant_mode",
                "geometry",
            ],
            "size": MAX_RESULTS,
        },
    )

    features = []
    for hit in result["hits"]["hits"]:
        src = hit["_source"]
        geom = src.pop("geometry", None)
        if geom and tolerance > 0:
            geom = _simplify(geom, tolerance)
        features.append(
            {"type": "Feature", "geometry": geom, "properties": src}
        )

    return jsonify({"type": "FeatureCollection", "features": features})
