import requests
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from . import schemas


class MLServerSettings(BaseSettings):
    """
    Settings for the ML server for NLP inference
    """

    host: str = Field(default="http://localhost:8004")
    api_key: str = Field(repr=False)
    request_timeout: int = Field(default=6, gt=0, le=60)

    model_config = SettingsConfigDict(env_prefix="ML_SERVER_")


class MLServerClient:
    """
    Client for the ML Server
    """

    def __init__(
        self, settings: MLServerSettings | None = None, request_timeout: int = 6
    ):
        self.__settings = settings or MLServerSettings()
        self.__session = requests.Session()
        self.__session.headers.update({"x-api-key": self.__settings.api_key})
        self.__timeout = request_timeout

    @property
    def settings(self) -> MLServerSettings:
        """
        Settings for ML inference client
        """
        return self.__settings

    def sentiment_analysis(self, text: str) -> dict[str, float]:
        """
        Call the ML inference server to perform sentiment analysis on a text
        :param text:
        :return:
        """
        rsp = self.__session.post(
            f"{self.settings.host}/api/sentiment",
            json={"text": text},
            timeout=self.settings.request_timeout,
        )
        rsp.raise_for_status()
        return rsp.json()["sentiment"]

    def emotion_detection(
        self, text: str, threshold: float = 0.5
    ) -> list[schemas.Emotion]:
        """
        Call the ML inference server to perform sentiment analysis on a text
        :param text:
        :param threshold: Probability threshold
        :return:
        """
        rsp = self.__session.post(
            f"{self.settings.host}/api/emotion",
            json={"text": text, "threshold": threshold},
            timeout=self.settings.request_timeout,
        )
        rsp.raise_for_status()
        return rsp.json()["emotions"]

    def text_embedding(self, text: str) -> list[float]:
        """
        Get the embedding vector for the given text.
        :param text:
        :return:
        """
        rsp = self.__session.post(
            f"{self.settings.host}/api/embed",
            json={"text": text},
            timeout=self.settings.request_timeout,
        )
        rsp.raise_for_status()
        return rsp.json()["embedding"]
