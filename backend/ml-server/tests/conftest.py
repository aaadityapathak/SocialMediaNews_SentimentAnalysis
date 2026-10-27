import pytest


@pytest.fixture(scope="session")
def inference_service():
    """
    Get an inference service for testing
    """
    from service import InferenceService, InferenceSettings

    settings = InferenceSettings(embeddings_enabled=True)
    return InferenceService(settings)
