"""
Script to create indices on ElasticSearch from specs stored in JSON files.

To run:

1. Start port forwarding to ElasticSearch instance:
```sh
export KUBECONFIG=path/to/kube/config
kubectl port-forward -n elastic svc/elasticsearch-es-http 9200:9200
```

2. Run with uv:
```
# Env file must have ElasticSearch API Key
uv run --env-file path/to/.env create_elasticsearch_idx.py --file path/to/file.json
```
"""

import json
import logging
from pathlib import Path
from elasticsearch import Elasticsearch
from typing import TypedDict, NotRequired

from elastic import ESSettings

logger = logging.getLogger(__name__)


class Property(TypedDict):
    """
    Property on an ElasticSearch Index Mapping definition
    """

    type: str
    index: NotRequired[bool]
    properties: NotRequired[dict[str, "Property"]]


class Mappings(TypedDict):
    """
    Mappings definition for ES Index
    """

    properties: dict[str, Property]


class IndexValue(TypedDict):
    """
    Value to index key
    """

    mappings: dict[str, Property]


def create_indices(
    client: Elasticsearch, definitions: dict[str, IndexValue]
) -> int:
    """
    Create the specified indices from the mappings on ElasticSearch
    :param client:
    :param definitions:
    :return: Total indices created
    """
    i = 0
    for k, v in definitions.items():
        rsp = client.indices.exists(index=k)
        if rsp.body:
            logger.debug("Index '%s' already exists - skipping", k)
            continue

        client.indices.create(index=k, mappings=v["mappings"])
        i += 1

    logger.info("Created %d indices", i)
    return i


def create_indices_from_file(file: Path | str) -> int:
    """
    Create ElasticSearch indices from definitions in a file.
    :param file:
    :return:
    """
    settings = ESSettings()
    client = Elasticsearch(
        settings.host,
        api_key=settings.api_key,
        # We don't need this since we will not expose
        # publicly and have no associated domain name
        verify_certs=False,
    )
    with open(file, "r") as f:
        spec = json.load(f)

    return create_indices(client, spec)


if __name__ == "__main__":
    import fire

    fire.Fire(create_indices_from_file)
