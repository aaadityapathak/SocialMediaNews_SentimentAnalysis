import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from elasticsearch import Elasticsearch
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from valkey import Valkey

from . import constants as const
from .base import BaseProcessor
from .schemas import SocialMediaRecord

logger = logging.getLogger(__name__)


class ValkeySettings(BaseSettings):
    """
    Settings to connect to valkey / redis for Keda orchestration and dispatch.
    """

    host: str = Field(default="localhost")
    port: int = Field(default=6379, gt=0)

    model_config = SettingsConfigDict(env_prefix="VALKEY_")


@dataclass
class Indexer:
    """
    Class to index documents into ElasticSearch
    """

    vk: Valkey
    es: Elasticsearch
    processors: dict[str, BaseProcessor]  # Map source name -> processor

    def insert(self, record: SocialMediaRecord):
        """
        Insert the document into the appropriate indices
        :param record:
        :return:
        """
        processor = self.processors[record.source]
        doc = record.data
        doc_id = processor.get_record_id(doc)
        index = processor.get_index(doc)

        # Check before normalization and inference so redelivery avoids the
        # expensive work. Independent checks repair partial deliveries.
        if record.save_provider_idx and not self.is_duplicated(index, doc_id):
            self.insert_to_index(
                index=index,
                document=processor.process_record(doc),
                document_id=doc_id,
                check_duplicate=False,
            )

        common_id = processor.build_common_id(doc_id)
        if record.save_common_idx and not self.is_duplicated(
            const.SOCIAL_POSTS_INDEX, common_id
        ):
            common_doc = processor.to_common_schema(doc)
            common_doc = processor.enrich_with_sentiment(common_doc)
            common_doc = processor.enrich_with_emotion_detection(common_doc)
            self.insert_to_index(
                index=const.SOCIAL_POSTS_INDEX,
                document=common_doc,
                document_id=common_id,
                check_duplicate=False,
            )

    def insert_to_index(
        self,
        index: str,
        document: dict,
        document_id: str,
        *,
        check_duplicate: bool = True,
    ):
        """
        Insert a document into the specified index. If it has been inserted
        in the deduplication window, this will be skipped.
        :param index:
        :param document:
        :param document_id:
        :return:
        """
        if check_duplicate and self.is_duplicated(index, document_id):
            logger.warning(
                "Common record has already been inserted to '%s': %s",
                index,
                document_id,
            )
            return

        self.es.index(index=index, document=document, id=document_id)
        self.register_insert(index, document_id)
        logger.debug("Document '%s' saved to '%s'", document_id, index)

    def is_duplicated(self, index: str, ident: str) -> bool:
        """
        Check if the given record ID for the index has been processed in the
        last two hours (and is therefore a duplicate).
        :param index:
        :param ident:
        :return:
        """
        key = f"check:{index}:{ident}"
        return self.vk.exists(key) > 0

    def register_insert(
        self, index: str, ident: str, window: timedelta | None = None
    ):
        """
        Register that the current record with given index and id has been
        inserted to ElasticSearch. This will prevent it from being inserted again
        in the next two hours.
        :param index:
        :param ident:
        :param window: Window of time in which to keep the record to prevent
            duplicate insertions.
        :return:
        """
        key = f"check:{index}:{ident}"
        self.vk.set(
            key,
            datetime.now(UTC).isoformat(timespec="seconds"),
            ex=window or timedelta(seconds=7200),
        )
