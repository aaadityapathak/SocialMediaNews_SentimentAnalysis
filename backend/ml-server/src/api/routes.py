from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from . import schemas as sch
from .dependency import check_api_key
from service import InferenceService

inf_service = InferenceService()

api_router = APIRouter(dependencies=[Depends(check_api_key)])


@api_router.post(
    "/sentiment",
    status_code=200,
    response_model=sch.SentimentResponse,
    response_class=JSONResponse,
)
def compute_sentiment(req: sch.SentimentRequest) -> sch.SentimentResponse:
    """
    Perform sentiment analysis on the given text.
    """
    result = inf_service.perform_sentiment_analysis(req.text)
    return sch.SentimentResponse(sentiment=sch.Sentiments(**result))


@api_router.post(
    "/emotion",
    status_code=200,
    response_model=sch.EmotionDetectResponse,
    response_class=JSONResponse,
)
def detect_emotions(req: sch.EmotionRequest) -> sch.EmotionDetectResponse:
    """
    Perform emotion detection on the given text.
    """
    result = inf_service.perform_emotion_detection(req.text)
    return sch.EmotionDetectResponse(
        emotions=list(map(sch.Label.model_validate, result))
    )


@api_router.post(
    "/embed",
    status_code=200,
    response_model=sch.EmbeddingResponse,
    response_class=JSONResponse,
)
def compute_embedding(req: sch.EmbedTextRequest) -> sch.EmbeddingResponse:
    """
    Compute the text embedding of the given text.
    """
    return sch.EmbeddingResponse(embedding=inf_service.embed_text(req.text))
