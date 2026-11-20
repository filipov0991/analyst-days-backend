from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Response
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError

from app import models, schemas
from app.api.dependencies import CurrentSession, DB, require_origin
from app.api.errors import APIException
from app.services.program import add_talk, read_program, remove_talk, talk_query

router = APIRouter(prefix="/api", responses={500: {"model": schemas.ApiError}})
validation = {422: {"model": schemas.ApiError}}
mutation_errors = {**validation, 403: {"model": schemas.ApiError}}
origin_documentation = {"parameters": [{"name": "origin", "in": "header", "required": True,
    "description": "Разрешённый Origin; отсутствие или несовпадение возвращает 403.",
    "schema": {"type": "string"}}]}
TalkId = Annotated[int, Path(gt=0)]
FilterId = Annotated[int | None, Query(gt=0)]


@router.get("/health", response_model=schemas.Health, responses={503: {"model": schemas.ApiError}})
def health(db: DB):
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError:
        raise APIException(503, "HEALTH_UNAVAILABLE", "База данных недоступна") from None
    return {"status": "ok", "database": "ok"}


@router.get("/conference", response_model=schemas.Conference)
def conference(db: DB):
    return dict(name="Analyst Days", timezone="Europe/Moscow", is_demo=True,
                demo_notice="Демонстрационная программа. Не является официальным расписанием Analyst Days",
                days=list(db.scalars(select(models.ConferenceDay).order_by(models.ConferenceDay.sort_order, models.ConferenceDay.id))),
                rooms=list(db.scalars(select(models.Room).order_by(models.Room.sort_order, models.Room.id))))


@router.get("/talks", response_model=schemas.TalkList, responses=validation)
def talks(db: DB, day_id: FilterId = None, room_id: FilterId = None):
    query = talk_query()
    if day_id is not None:
        query = query.where(models.Talk.day_id == day_id)
    if room_id is not None:
        query = query.where(models.Talk.room_id == room_id)
    items = list(db.scalars(query))
    return dict(items=items, total=len(items))


@router.get("/talks/{talk_id}", response_model=schemas.Talk, responses={**validation, 404: {"model": schemas.ApiError}})
def talk(talk_id: TalkId, db: DB):
    found = db.get(models.Talk, talk_id)
    if found is None:
        raise APIException(404, "TALK_NOT_FOUND", "Доклад не найден")
    return found


@router.get("/me/program", response_model=schemas.Program)
def program(db: DB, session_id: CurrentSession):
    return read_program(db, session_id)


@router.put("/me/program/talks/{talk_id}", response_model=schemas.Program,
            dependencies=[Depends(require_origin)], openapi_extra=origin_documentation, responses={**mutation_errors, 404: {"model": schemas.ApiError}})
def select_talk(talk_id: TalkId, db: DB, session_id: CurrentSession):
    talk(talk_id, db)
    db.commit()  # End the existence check before the atomic insert transaction.
    add_talk(db, session_id, talk_id)
    return read_program(db, session_id)


@router.delete("/me/program/talks/{talk_id}", status_code=204, response_class=Response,
               dependencies=[Depends(require_origin)], openapi_extra=origin_documentation, responses=mutation_errors)
def deselect_talk(talk_id: TalkId, db: DB, session_id: CurrentSession):
    remove_talk(db, session_id, talk_id)
    return Response(status_code=204)
