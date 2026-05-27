import logging
from flask import request
from valkey import Valkey
from pydantic import ValidationError
from elasticsearch import Elasticsearch

import processing as proc
from base import setup_logging
from elastic import ESSettings
from base.read_fission_cfg import read_from_secret

setup_logging()
logger = logging.getLogger(__name__)


def load_social_to_es():
    """
    Load Social Media posts to Elasticsearch
    """
    es_settings = read_from_secret("elastic-api-credentials", ESSettings)
    vk_settings = read_from_secret("valkey-cfg", proc.ValkeySettings)
    ml_settings = read_from_secret("ml-server-access", proc.MLServerSettings)
    es = Elasticsearch(
        es_settings.host, api_key=es_settings.api_key, verify_certs=False
    )
    vk = Valkey(host=vk_settings.host, port=vk_settings.port)
    ml = proc.MLServerClient(ml_settings)

    try:
        parsed = proc.schemas.RecordAdapter.validate_json(request.get_data())
        logger.info("Got data for inserting to ES from '%s'", parsed.source)

        indexer = proc.build_indexer(es, vk, ml)
        indexer.insert(parsed)

        logger.debug("DONE")
        return "ok"

    except ValidationError as e:
        logger.error("Invalid data schema received: %s", str(e))
        return str(e), 422

    except Exception as e:
        logger.error(
            "Unhandled error encountered in processing [%s.%s] %s",
            type(e).__module__,
            type(e).__name__,
            str(e),
        )
        return "Unhandled error in function", 500
