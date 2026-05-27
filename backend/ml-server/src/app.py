from fastapi import FastAPI
from fastapi.responses import JSONResponse

from api.routes import api_router
from api.schemas import SuccessResponse

app = FastAPI(title="Inference Helper")

app.include_router(api_router, prefix="/api")


@app.get(
    "/health",
    response_class=JSONResponse,
    response_model=SuccessResponse,
    status_code=200,
)
def health_check():
    """
    Basic healthcheck endpoint.
    :return:
    """
    return SuccessResponse()
