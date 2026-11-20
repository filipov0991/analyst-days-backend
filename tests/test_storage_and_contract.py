import json

from datetime import UTC, datetime, time, timedelta
from itertools import combinations
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select, text
from sqlalchemy.exc import IntegrityError

from app.config import Settings
from app.db import UTCDateTime
from app.main import create_app
from app.models import AnonymousSession, ConferenceDay, Room, SelectedTalk, Speaker, Talk
from app.services.conflicts import find_conflicts


def test_seed_integrity(application):
    with application.state.sessions() as db:
        for model, count in ((ConferenceDay, 2), (Room, 3), (Speaker, 20), (Talk, 20)):
            assert db.scalar(select(func.count()).select_from(model)) == count
        days = {d.id: d.date for d in db.scalars(select(ConferenceDay))}
        talks = list(db.scalars(select(Talk)))
        for talk in talks:
            assert talk.starts_at.astimezone(ZoneInfo("Europe/Moscow")).date() == days[talk.day_id]
            assert talk.ends_at > talk.starts_at
        for a, b in combinations(talks, 2):
            if a.room_id == b.room_id:
                assert not find_conflicts([a, b])


def test_timezone_round_trip(application):
    with application.state.sessions() as db:
        day = db.get(ConferenceDay, 1)
        instant = datetime.combine(day.date, time(0, 15), ZoneInfo("Europe/Moscow"))
        talk = db.get(Talk, 1)
        talk.starts_at, talk.ends_at = instant, instant + timedelta(hours=1)
        db.commit()
        db.expire_all()
        assert talk.starts_at == instant.astimezone(UTC)
        assert talk.starts_at.tzinfo == UTC
        raw = db.execute(text("SELECT starts_at FROM talks WHERE id=1")).scalar_one()
        assert raw == instant.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S.%f")
    with TestClient(application) as client:
        assert client.get("/api/talks/1").json()["starts_at"] == instant.astimezone(UTC).isoformat().replace("+00:00", "Z")
    with pytest.raises(ValueError):
        UTCDateTime().process_bind_param(datetime(2031, 1, 1), None)
    with application.state.sessions() as db:
        talk = db.get(Talk, 1)
        talk.starts_at += timedelta(days=5)
        talk.ends_at += timedelta(days=5)
        with pytest.raises(ValueError, match="conference day"):
            db.commit()


def test_constraints_and_cascades(application, client, origin):
    with application.state.sessions() as db:
        assert db.execute(text("PRAGMA foreign_keys")).scalar_one() == 1
        assert db.execute(text("PRAGMA busy_timeout")).scalar_one() == 5000
        talk = db.get(Talk, 1)
        talk.ends_at = talk.starts_at
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
        db.add(SelectedTalk(session_id=999, talk_id=1, created_at=datetime.now(UTC)))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
    client.put("/api/me/program/talks/1", headers=origin)
    with application.state.sessions.begin() as db:
        db.execute(delete(Talk).where(Talk.id == 1))
    assert client.get("/api/me/program").json()["selected_count"] == 0
    client.put("/api/me/program/talks/2", headers=origin)
    with application.state.sessions.begin() as db:
        db.execute(delete(AnonymousSession))
    with application.state.sessions() as db:
        assert db.scalar(select(func.count()).select_from(SelectedTalk)) == 0


def test_secure_cookie(tmp_path):
    settings = Settings(_env_file=None, database_url=f"sqlite:///{tmp_path / 'secure.db'}", cookie_secure=True, app_env="production")
    app = create_app(settings)
    from app.seed import seed
    seed(app.state.engine)
    with TestClient(app, base_url="https://testserver") as client:
        assert "Secure" in client.get("/api/me/program").headers["set-cookie"]
    with pytest.raises(ValueError):
        Settings(_env_file=None, app_env="production", cookie_secure=False)


def test_unavailable_database_and_internal_errors(tmp_path, caplog):
    app = create_app(Settings(_env_file=None, database_url=f"sqlite:///{tmp_path / 'missing' / 'app.db'}"))
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/api/health")
        assert response.status_code == 503
        assert response.json()["error"] == {"code": "HEALTH_UNAVAILABLE", "message": "База данных недоступна", "details": []}
        response = client.get("/api/me/program", headers={"Cookie": "ad_session=do-not-log-this-secret"})
        assert response.status_code == 500
        assert response.json()["error"]["code"] == "INTERNAL_ERROR"
        assert response.headers["cache-control"] == "no-store"
        assert "Traceback" not in response.text
        assert "do-not-log-this-secret" not in caplog.text
        assert "OperationalError" in caplog.text


def test_openapi(client):
    assert client.get("/docs").status_code == 200
    schema = client.get("/openapi.json").json()
    paths = schema["paths"]
    assert set(paths) == {"/api/health", "/api/conference", "/api/talks", "/api/talks/{talk_id}",
                          "/api/me/program", "/api/me/program/talks/{talk_id}"}
    models = schema["components"]["schemas"]
    expected = {
        "Day": {"id", "label", "date", "sort_order"},
        "Room": {"id", "name", "sort_order"},
        "Speaker": {"id", "name", "bio"},
        "Talk": {"id", "day_id", "title", "description", "topic", "starts_at", "ends_at", "room", "speaker"},
        "Conference": {"name", "timezone", "is_demo", "demo_notice", "days", "rooms"},
        "Conflict": {"talk_id", "conflicting_talk_ids"},
        "Program": {"talks", "conflicts", "selected_count", "conflicting_talk_count"},
        "ApiError": {"error"},
        "ErrorBody": {"code", "message", "details"},
    }
    for name, fields in expected.items():
        assert set(models[name]["properties"]) == fields
        assert set(models[name]["required"]) == fields
        assert '"type": "null"' not in json.dumps(models[name])
    for path in paths.values():
        for operation in path.values():
            assert "requestBody" not in operation
            for status, response in operation["responses"].items():
                if int(status) >= 400:
                    assert response["content"]["application/json"]["schema"]["$ref"].endswith("/ApiError")
    mutation = paths["/api/me/program/talks/{talk_id}"]
    assert "content" not in mutation["delete"]["responses"]["204"]
    for method in ("put", "delete"):
        assert any(p["name"] == "origin" and p["in"] == "header" and p["required"] for p in mutation[method]["parameters"])


@pytest.mark.parametrize("offset,duration,conflict", [(0, 60, True), (30, 60, True), (15, 15, True), (60, 30, False), (1440, 60, False)])
def test_interval_edges(offset, duration, conflict):
    base = datetime(2031, 1, 1, tzinfo=UTC)
    a = Talk(id=1, starts_at=base, ends_at=base + timedelta(minutes=60))
    b = Talk(id=2, starts_at=base + timedelta(minutes=offset), ends_at=base + timedelta(minutes=offset + duration))
    result = find_conflicts([a, b])
    assert bool(result) is conflict
    if conflict:
        assert [item.model_dump() for item in result] == [
            {"talk_id": 1, "conflicting_talk_ids": [2]}, {"talk_id": 2, "conflicting_talk_ids": [1]}]
    assert find_conflicts([a, a]) == []
