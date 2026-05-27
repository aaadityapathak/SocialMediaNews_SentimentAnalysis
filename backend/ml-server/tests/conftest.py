import pytest

from service import InferenceService, InferenceSettings


@pytest.fixture(scope="session")
def inference_service() -> InferenceService:
    """
    Get an inference service for testing
    """
    settings = InferenceSettings(embeddings_enabled=True)
    return InferenceService(settings)
