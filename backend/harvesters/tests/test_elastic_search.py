import json
import time
import pytest
from typing import Iterator
from elasticsearch import Elasticsearch
from pydantic import BaseModel
from datetime import datetime, UTC

from create_elasticsearch_idx import create_indices_from_file, create_indices


class IdxSubModel1(BaseModel):
    """
    Nexted in idx1 model
    """

    sub_string: str
    sub_string_2: str | None = None


class Idx1Model(BaseModel):
    """
    Model for test index 1
    """

    number_prop: int
    kw_prop: str
    text_field: str
    time_field: datetime
    sub_list: list[IdxSubModel1]


@pytest.fixture(scope="session")
def create_test_indices(
    es_settings, indices_definition
) -> Iterator[tuple[str, str]]:
    """
    Create a pair of indices for testing.
    :param es_settings:
    :param indices_definition:
    """
    with open(indices_definition, "r") as f:
        defs = json.load(f)

    # Rename to avoid collisions with other tests
    i1_name, i2_name = "test-idx-a", "test-idx-b"
    defs[i1_name] = defs.pop("test-index-1")
    defs[i2_name] = defs.pop("test-index-2")

    client = Elasticsearch(
        es_settings.host, api_key=es_settings.api_key, verify_certs=False
    )

    create_indices(client, defs)
    yield i1_name, i2_name

    client.indices.delete(index=i1_name)
    client.indices.delete(index=i2_name)


def test_create_indices(indices_definition, es_client):
    """
    Test that indices can be created from config file
    """

    created = create_indices_from_file(indices_definition)
    assert created == 2, "Expected 2 test indices to be created"

    es_client.indices.delete(index="test-index-1")
    es_client.indices.delete(index="test-index-2")


def test_index_schema(create_test_indices, es_client):
    """
    Test that documents loaded to indices retain the correct schema.
    :param create_test_indices:
    """
    i1, _ = create_test_indices
    now = datetime.now(UTC)
    document = {
        "number_prop": 24,
        "kw_prop": "key",
        "text_field": "This is an example text",
        "time_field": now,
        "sub_list": [
            {"sub_string": "nested"},
            {"sub_string": "another", "sub_string_2": "object"},
        ],
    }
    es_client.index(id="test_schema_1", index=i1, document=document)

    # Time to propagate
    time.sleep(1)
    rsp = es_client.get(index=i1, id="test_schema_1")
    retrieved = rsp["_source"]

    parsed = Idx1Model.model_validate(retrieved)

    assert parsed.kw_prop == document["kw_prop"]
    assert parsed.number_prop == document["number_prop"]
    assert parsed.text_field == document["text_field"]
    assert parsed.sub_list[0].sub_string_2 is None
    assert (
        parsed.sub_list[0].sub_string == document["sub_list"][0]["sub_string"]
    )
    assert parsed.time_field == now
