from api.settings import get_server_settings


if __name__ == "__main__":
    import uvicorn

    settings = get_server_settings()
    uvicorn.run("app:app", host=settings.host, port=settings.port)
