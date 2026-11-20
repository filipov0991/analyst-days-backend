from datetime import date
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, PositiveInt


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Day(ORMModel):
    id: PositiveInt
    label: str
    date: date
    sort_order: int


class Room(ORMModel):
    id: PositiveInt
    name: str
    sort_order: int


class Speaker(ORMModel):
    id: PositiveInt
    name: str
    bio: str


class Talk(ORMModel):
    id: PositiveInt
    day_id: PositiveInt
    title: str
    description: str
    topic: str
    starts_at: AwareDatetime
    ends_at: AwareDatetime
    room: Room
    speaker: Speaker


class Conference(BaseModel):
    name: str
    timezone: Literal["Europe/Moscow"]
    is_demo: bool
    demo_notice: str
    days: list[Day]
    rooms: list[Room]


class TalkList(BaseModel):
    items: list[Talk]
    total: int


class Conflict(BaseModel):
    talk_id: PositiveInt
    conflicting_talk_ids: list[PositiveInt]


class Program(BaseModel):
    talks: list[Talk]
    conflicts: list[Conflict]
    selected_count: int
    conflicting_talk_count: int


class ErrorDetail(BaseModel):
    field: str
    message: str


class ErrorBody(BaseModel):
    code: str
    message: str
    details: list[ErrorDetail]


class ApiError(BaseModel):
    error: ErrorBody


class Health(BaseModel):
    status: Literal["ok"]
    database: Literal["ok"]
