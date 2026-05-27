from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class InferenceSettings(BaseSettings):
    """
    Settings for inference server.
    """

    models_path: Path = Path(__file__).parents[2] / "hf-models"

    sentiment_model: str = "cardiffnlp/twitter-roberta-base-sentiment-latest"
    embedding_model: str = "sentence-transformers/all-mpnet-base-v2"
    embeddings_enabled: bool = False

    model_config = SettingsConfigDict(env_prefix="INFERENCE_")
