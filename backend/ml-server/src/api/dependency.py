from fastapi import Depends, HTTPException
from fastapi.security import APIKeyHeader

from .settings import get_server_settings

_settings = get_server_settings()
_header = APIKeyHeader(name="x-api-key")


def check_api_key(header: str = Depends(_header)):
    """
    Basic dependency for simple authentication with single API key. Suitable
    for this simple use case, since we will handle only public data.
    :param header:
    :return:
    """
    if header != _settings.api_key:
        raise HTTPException(status_code=403, detail="Unauthorised")
