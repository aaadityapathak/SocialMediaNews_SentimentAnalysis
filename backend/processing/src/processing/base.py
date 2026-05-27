import re
import logging
from typing import Any
from html import unescape
from datetime import datetime, UTC
from abc import ABC, abstractmethod

from .schemas import CommonRecord, Sentiment
from .ml_client import MLServerClient

logger = logging.getLogger(__name__)


class BaseProcessor(ABC):
    """
    Processor to transform records for insertion.
    """

    def __init__(self, inference: MLServerClient):
        self.__inference = inference

    @property
    def inference(self) -> MLServerClient:
        """
        ML Inference client
        """
        return self.__inference

    def enrich_with_emotion_detection(
        self, record: CommonRecord
    ) -> CommonRecord:
        """
        Attempt to add emotion detection to a common record.
        Logs and skips on failure. This step is non-essential.
        :param record:
        :return:
        """
        text = record.get("text", "")
        if not text:
            return record
        try:
            emotes = self.inference.emotion_detection(text)
            record["emotion"] = emotes
            logger.info("Emotion detection complete")
        except Exception as exc:
            logger.error(
                "Emotion detection failed for '%s': [%s.%s] %s",
                record.get("common_id"),
                type(exc).__module__,
                type(exc).__name__,
                exc,
            )
            raise ValueError("Unable to complete emotion detection")
        return record

    def enrich_with_sentiment(self, record: CommonRecord) -> CommonRecord:
        """
        Attempt to add sentiment analysis to a common record.
        Logs and skips on failure. Sentiment is non-essential.
        :param record:
        :return:
        """
        text = record.get("text", "")
        if not text:
            return record
        try:
            scores = self.inference.sentiment_analysis(text)
            dominant = max(
                ("positive", "neutral", "negative"), key=scores.__getitem__
            )
            record["sentiment"] = Sentiment(  # noqa: PGH003
                positive=scores.get("positive", 0.0),
                neutral=scores.get("neutral", 0.0),
                negative=scores.get("negative", 0.0),
                sentiment=dominant,
            )
            logger.info("Sentiment analysis complete")
        except Exception as exc:
            logger.error(
                "Sentiment analysis failed for '%s': [%s.%s] %s",
                record.get("common_id"),
                type(exc).__module__,
                type(exc).__name__,
                exc,
            )
            raise ValueError("Unable to complete sentiment analysis")
        return record

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(UTC).isoformat()

    @staticmethod
    def _clean_text(text: str | None) -> str:
        """
        Convert HTML-ish / messy text into a cleaner plain-text string.
        Good enough for common-index sentiment analysis.
        """
        if not text:
            return ""

        text = unescape(text)
        text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
        text = re.sub(r"</p\s*>", "\n", text, flags=re.IGNORECASE)
        text = re.sub(r"<[^>]+>", "", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    def build_common_id(self, platform_post_id: str) -> str:
        """
        Build ID for common schema
        :param platform_post_id:
        :return:
        """
        return f"{self.provider}-{platform_post_id}"

    @property
    @abstractmethod
    def provider(self) -> str:
        """
        Name of the provider / source of the records
        """
        pass

    @abstractmethod
    def get_index(self, doc: Any) -> str:
        """
        Elasticsearch index for this record.
        """
        pass

    @abstractmethod
    def get_record_id(self, doc: Any) -> str:
        """
        Get the record's identifier.
        :param doc:
        :return:
        """
        pass

    @abstractmethod
    def to_common_schema(self, doc: Any) -> CommonRecord:
        """
        Convert a record into the common schema.
        :param doc:
        :return:
        """
        pass

    @abstractmethod
    def process_record(self, doc: Any) -> dict:
        """
        Process a record for insertion to the provider schema.
        :param doc:
        :return:
        """
        pass
