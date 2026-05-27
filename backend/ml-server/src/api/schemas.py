from pydantic import BaseModel, model_validator, Field


class SuccessResponse(BaseModel):
    """
    Generic success response
    """

    message: str = "ok"


class EmbedTextRequest(BaseModel):
    """
    Request to compute a text embedding
    """

    text: str


class SentimentRequest(BaseModel):
    """
    Request to perform sentiment analysis on a text
    """

    text: str


class EmotionRequest(BaseModel):
    """
    Request to perform emotion detection on a given text
    """

    text: str
    threshold: float = Field(
        default=0.5,
        gt=0.0,
        lt=1.0,
        description="Probability threshold to keep emotion tags",
    )


class Sentiments(BaseModel):
    """
    Sentiment values inferred from a text
    """

    positive: float | None = None
    neutral: float | None = None
    negative: float | None = None

    @model_validator(mode="after")
    def check_values(self):
        """
        Check that at least one of the values for sentiment is set.
        """
        if (
            self.positive is None
            and self.negative is None
            and self.neutral is None
        ):
            raise ValueError("At least one sentiment score must be given")
        return self


class SentimentResponse(BaseModel):
    """
    Response to a request for sentiment analysis.
    """

    sentiment: Sentiments


class EmbeddingResponse(BaseModel):
    """
    Response to a request for model embeddings
    """

    embedding: list[float]


class Label(BaseModel):
    """
    A label from extracting tags from text
    """

    label: str
    score: float


class EmotionDetectResponse(BaseModel):
    """
    Response from the Emotion Detection endpoint
    """

    emotions: list[Label]
