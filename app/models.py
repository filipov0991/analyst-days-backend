from datetime import date as Date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import CheckConstraint, ForeignKey, String, event
from sqlalchemy.orm import Mapped, Session, mapped_column, relationship

from app.db import Base, UTCDateTime


class ConferenceDay(Base):
    __tablename__ = "conference_days"
    id: Mapped[int] = mapped_column(primary_key=True)
    label: Mapped[str]
    date: Mapped[Date] = mapped_column(unique=True)
    sort_order: Mapped[int]


class Room(Base):
    __tablename__ = "rooms"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(unique=True)
    sort_order: Mapped[int]


class Speaker(Base):
    __tablename__ = "speakers"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    bio: Mapped[str]


class Talk(Base):
    __tablename__ = "talks"
    __table_args__ = (CheckConstraint("ends_at > starts_at", name="positive_duration"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    day_id: Mapped[int] = mapped_column(ForeignKey("conference_days.id"), index=True)
    room_id: Mapped[int] = mapped_column(ForeignKey("rooms.id"), index=True)
    speaker_id: Mapped[int] = mapped_column(ForeignKey("speakers.id"), index=True)
    title: Mapped[str]
    description: Mapped[str]
    topic: Mapped[str]
    starts_at: Mapped[datetime] = mapped_column(UTCDateTime(), index=True)
    ends_at: Mapped[datetime] = mapped_column(UTCDateTime())
    room: Mapped[Room] = relationship(lazy="joined")
    speaker: Mapped[Speaker] = relationship(lazy="joined")


class AnonymousSession(Base):
    __tablename__ = "anonymous_sessions"
    id: Mapped[int] = mapped_column(primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime())
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime())


class SelectedTalk(Base):
    __tablename__ = "selected_talks"
    session_id: Mapped[int] = mapped_column(ForeignKey("anonymous_sessions.id", ondelete="CASCADE"), primary_key=True)
    talk_id: Mapped[int] = mapped_column(ForeignKey("talks.id", ondelete="CASCADE"), primary_key=True, index=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime())


# Application writes must preserve the local conference day. There is no public
# write API for the catalog; the seed checks this invariant before bulk inserts.
@event.listens_for(Session, "before_flush")
def validate_talk_day(db, flush_context, instances):
    for entity in db.new.union(db.dirty):
        if isinstance(entity, Talk):
            day = db.get(ConferenceDay, entity.day_id)
            if day is None:
                continue  # The foreign key constraint reports a missing day.
            start = entity.starts_at
            if start.tzinfo is None or start.utcoffset() is None:
                raise ValueError("A timezone-aware datetime is required")
            if start.astimezone(ZoneInfo("Europe/Moscow")).date() != day.date:
                raise ValueError("Talk start must match the conference day in Europe/Moscow")
