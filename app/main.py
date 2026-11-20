from contextlib import asynccontextmanager

from fastapi import FastAPI, Request

from app.api.errors import internal_error, register_handlers
from app.api.routes import router
from app.config import Settings
from app.db import build_engine, session_factory
from app.services.sessions import COOKIE_NAME, SESSION_SECONDS


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    engine = build_engine(settings.database_url)

    @asynccontextmanager
    async def lifespan(app):
        yield
        engine.dispose()

    app = FastAPI(title="Analyst Days: моя программа", version="1.0.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.engine = engine
    app.state.sessions = session_factory(engine)
    register_handlers(app)

    @app.middleware("http")
    async def session_transport(request: Request, call_next):
        try:
            response = await call_next(request)
        except Exception as exc:
            response = internal_error(exc)
        if request.url.path.startswith("/api/me/"):
            response.headers["Cache-Control"] = "no-store"
            token = getattr(request.state, "new_session_token", None)
            if token:
                response.set_cookie(COOKIE_NAME, token, max_age=SESSION_SECONDS, httponly=True,
                                    secure=settings.cookie_secure, samesite="lax", path="/")
        return response

    app.include_router(router)
    return app


app = create_app()
