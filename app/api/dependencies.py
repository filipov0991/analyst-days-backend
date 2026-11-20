from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.api.errors import APIException
from app.services.sessions import COOKIE_NAME, resolve_session


def get_db(request: Request):
    with request.app.state.sessions() as db:
        yield db


DB = Annotated[Session, Depends(get_db)]


def current_session(request: Request, db: DB) -> int:
    session_id, new_token = resolve_session(db, request.cookies.get(COOKIE_NAME))
    if new_token:
        request.state.new_session_token = new_token
    return session_id


CurrentSession = Annotated[int, Depends(current_session)]


def require_origin(request: Request):
    origin = request.headers.get("origin")
    if origin is None or origin not in request.app.state.settings.origins:
        raise APIException(403, "ORIGIN_NOT_ALLOWED", "Origin не разрешён")
