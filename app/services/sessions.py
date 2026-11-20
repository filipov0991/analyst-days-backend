import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AnonymousSession

COOKIE_NAME = "ad_session"
SESSION_SECONDS = 30 * 24 * 60 * 60


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def resolve_session(db: Session, token: str | None) -> tuple[int, str | None]:
    now = datetime.now(UTC)
    if token:
        current = db.scalar(select(AnonymousSession).where(
            AnonymousSession.token_hash == token_hash(token), AnonymousSession.expires_at > now))
        # Finish the read transaction before any write to avoid SQLite lock upgrades.
        db.commit()
        if current:
            return current.id, None
    token = secrets.token_urlsafe(32)
    current = AnonymousSession(token_hash=token_hash(token), created_at=now,
                               expires_at=now + timedelta(seconds=SESSION_SECONDS))
    db.add(current)
    db.commit()
    return current.id, token
