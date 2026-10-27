import logging
from contextlib import ExitStack

import processing as proc
from base import setup_logging
from base.read_fission_cfg import read_from_secret
from elastic import ESSettings
from elasticsearch import Elasticsearch
from flask import request
from pydantic import ValidationError
from valkey import Valkey

setup_logging()
logger = logging.getLogger(__name__)


def load_social_to_es():
    """
    Load Social Media posts to Elasticsearch
    """
    try:
        parsed = proc.schemas.RecordAdapter.validate_json(request.get_data())
    except ValidationError as e:
        logger.error("Invalid data schema received: %s", str(e))
        return str(e), 422

    try:
        es_settings = read_from_secret("elastic-api-credentials", ESSettings)
        vk_settings = read_from_secret("valkey-cfg", proc.ValkeySettings)
        ml_settings = read_from_secret(
            "ml-server-access", proc.MLServerSettings
        )
        logger.info("Got data for inserting to ES from '%s'", parsed.source)
        with ExitStack() as clients:
            es = Elasticsearch(
                es_settings.host,
                api_key=es_settings.api_key,
                verify_certs=False,
            )
            clients.callback(es.close)
            vk = Valkey(host=vk_settings.host, port=vk_settings.port)
            clients.callback(vk.close)
            ml = proc.MLServerClient(ml_settings)
            clients.callback(ml.close)
            proc.build_indexer(es, vk, ml).insert(parsed)

        logger.debug("DONE")
        return "ok"

    except Exception as e:  # noqa: BLE001 - translate failures at the HTTP boundary
        logger.error(
            "Unhandled error encountered in processing [%s.%s] %s",
            type(e).__module__,
            type(e).__name__,
            str(e),
        )
        return "Unhandled error in function", 500
