from fastapi import FastAPI

from .oauth_router import make_router


def make_app(
    *, store, master_secret: bytes, state_secret: bytes, redirect_uri: str, on_connected=None
) -> FastAPI:
    app = FastAPI(title="Conexus OAuth")
    app.include_router(make_router(
        store=store, master_secret=master_secret, state_secret=state_secret,
        redirect_uri=redirect_uri, on_connected=on_connected))
    return app
