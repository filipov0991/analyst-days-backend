from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session

from app.models import Room, SelectedTalk, Talk
from app.schemas import Program
from app.services.conflicts import find_conflicts


def talk_query():
    return select(Talk).join(Room).order_by(Talk.starts_at, Room.sort_order, Talk.id)


def read_program(db: Session, session_id: int) -> Program:
    talks = list(db.scalars(talk_query().join(SelectedTalk).where(SelectedTalk.session_id == session_id)))
    conflicts = find_conflicts(talks)
    return Program(talks=talks, conflicts=conflicts, selected_count=len(talks), conflicting_talk_count=len(conflicts))


def add_talk(db: Session, session_id: int, talk_id: int):
    db.execute(insert(SelectedTalk).values(session_id=session_id, talk_id=talk_id, created_at=datetime.now(UTC))
               .on_conflict_do_nothing(index_elements=["session_id", "talk_id"]))
    db.commit()


def remove_talk(db: Session, session_id: int, talk_id: int):
    db.execute(delete(SelectedTalk).where(SelectedTalk.session_id == session_id, SelectedTalk.talk_id == talk_id))
    db.commit()
