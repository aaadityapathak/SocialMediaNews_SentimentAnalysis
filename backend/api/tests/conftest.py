import pytest
from pathlib import Path
from typing import Iterator

from settings import ESSettings
from api_schemas import TrendsRequest
from elasticsearch import Elasticsearch

from time_series import get_emotions_timeseries, get_sentiment_timeseries


@pytest.fixture(scope="session", autouse=True)
def load_env():
    """
    Load environment variables from env file in api component root.
    :return:
    """
    import dotenv

    dotenv.load_dotenv(Path(__file__).parents[1] / ".env")


@pytest.fixture()
def es_settings() -> ESSettings:
    return ESSettings(host="https://localhost:9200")


@pytest.fixture()
def es_client(es_settings) -> Iterator[Elasticsearch]:

    es = Elasticsearch(
        es_settings.host,
        api_key=es_settings.api_key,
        verify_certs=False,
        ssl_show_warn=False,
    )
    with es:
        yield es
