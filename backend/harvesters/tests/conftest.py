import pytest
import dotenv
from pathlib import Path
from elasticsearch import Elasticsearch

from elastic import ESSettings
import mastodon_retrieve as mast


_ENV_PATH: Path = Path(__file__).parents[1] / ".env"


@pytest.fixture(scope="session")
def indices_definition() -> Path:
    """
    Path to file with ElasticSearch test index definition
    :return:
    """
    return Path(__file__).parents[3] / "database" / "mappings" / "test-indices.json"


@pytest.fixture()
def mastodon_settings_no_auth() -> mast.MastodonSettings:
    """
    Get mastodon settings with no auth token
    :return:
    """
    return mast.MastodonSettings(
        auth_token=None,
        user_agent="unimelb-c90024-test",
        base_url="https://mastodon.au",
    )


@pytest.fixture(scope="session")
def es_settings(scope="session") -> ESSettings:
    """
    ElasticSearch settings for tests
    :return:
    """
    return ESSettings(
        host="https://localhost:9200"  # Enforce local host (port forward to k8s)
    )


@pytest.fixture(scope="session")
def es_client(es_settings) -> Elasticsearch:
    """
    ElasticSearch client
    :param es_settings:
    :return:
    """
    return Elasticsearch(
        es_settings.host, api_key=es_settings.api_key, verify_certs=False
    )


@pytest.fixture(scope="session", autouse=True)
def load_env():
    """
    Load environment variables from 'backend/harvesters/.env'
    :return:
    """
    dotenv.load_dotenv(_ENV_PATH)
