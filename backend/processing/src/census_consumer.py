import json
import logging

from base import setup_logging
from base.read_fission_cfg import read_from_secret
from elastic import ESSettings
from elasticsearch import Elasticsearch
from flask import request
from processing.process_census import CENSUS_INDEX

setup_logging()
log = logging.getLogger(__name__)


def load_census_to_es():
    es_settings = read_from_secret("elastic-api-credentials", ESSettings)
    es = Elasticsearch(
        es_settings.host, api_key=es_settings.api_key, verify_certs=False
    )

    with es:
        record = json.loads(request.get_data())
        doc_id = record.pop("_id")
        es.update(
            index=CENSUS_INDEX,
            id=doc_id,
            body={"doc": record, "doc_as_upsert": True},
        )
    log.info("Upserted %s/%s", CENSUS_INDEX, doc_id)
    return {"status": "ok", "id": doc_id}
