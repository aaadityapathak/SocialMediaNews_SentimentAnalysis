from functools import cached_property
from fastapi import HTTPException, status
from optimum.onnxruntime import ORTModelForSequenceClassification
from sentence_transformers import SentenceTransformer
from transformers import AutoTokenizer, pipeline

from .settings import InferenceSettings


class InferenceService:
    """
    Inference service to compute sentiment analysis and text embeddings
    """

    def __init__(self, settings: InferenceSettings | None = None):
        self.__settings = settings or InferenceSettings()
        sentiment_dir = self.__settings.models_path / "sentiment"
        emotion_dir = self.__settings.models_path / "emotion"

        sentiment_model = ORTModelForSequenceClassification.from_pretrained(
            sentiment_dir
        )
        sentiment_tokenizer = AutoTokenizer.from_pretrained(sentiment_dir)
        self.__sentiment = pipeline(
            "text-classification",
            model=sentiment_model,
            tokenizer=sentiment_tokenizer,
        )

        emotion_model = ORTModelForSequenceClassification.from_pretrained(
            emotion_dir
        )
        emotion_tokenizer = AutoTokenizer.from_pretrained(emotion_dir)
        self.__emotion = pipeline(
            "text-classification",
            model=emotion_model,
            tokenizer=emotion_tokenizer,
            top_k=None,
        )

    @cached_property
    def __embed(self) -> SentenceTransformer:
        """
        Lazily loaded embeddings model
        :return:
        """
        embedding_dir = self.__settings.models_path / "embeddings"
        return SentenceTransformer(
            str(embedding_dir),
            backend="onnx",
            model_kwargs={"file_name": "onnx/model_qint8_avx512_vnni.onnx"},
        )

    def embed_text(self, text: str) -> list[float]:
        """
        Compute the text embedding of the given text.
        :return:
        """
        if not self.__settings.embeddings_enabled:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Embeddings model not currently enabled",
            )
        result = self.__embed.encode([text])
        return result[0, :].tolist()

    def perform_sentiment_analysis(self, text: str) -> dict:
        """
        Perform sentiment analysis on the given text.
        :param text:
        :return:
        """
        sentiments = self.__sentiment([text], top_k=3)[0]
        return {elem["label"]: elem["score"] for elem in sentiments}

    def perform_emotion_detection(
        self, text: str, threshold: float = 0.5
    ) -> list[dict]:
        """
        Perform emotion detection on the given text.
        :param text:
        :param threshold:
        :return:
        """
        emotions = self.__emotion([text])[0]
        return [entry for entry in emotions if entry.get("score") >= threshold]  # noqa
