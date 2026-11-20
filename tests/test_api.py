from datetime import UTC, datetime, timedelta
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.main import create_app
from app.models import AnonymousSession, SelectedTalk, Talk
from app.seed import seed
from app.services.sessions import token_hash

PROGRAM = "/api/me/program"


def put(client, id_, origin):
    response = client.put(f"{PROGRAM}/talks/{id_}", headers=origin)
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    return response.json()


def test_catalog(client):
    assert client.get("/api/health").json() == {"status": "ok", "database": "ok"}
    conference = client.get("/api/conference").json()
    assert conference["is_demo"] is True
    assert "Не является официальным" in conference["demo_notice"]
    assert [d["label"] for d in conference["days"]] == ["День 1", "День 2"]
    assert len(conference["rooms"]) == 3
    items = client.get("/api/talks").json()
    assert items["total"] == len(items["items"]) == 20
    assert items["items"] == sorted(items["items"], key=lambda t: (t["starts_at"], t["room"]["sort_order"], t["id"]))
    for talk in items["items"]:
        assert talk["starts_at"].endswith("Z") and talk["ends_at"].endswith("Z")
        assert client.get(f"/api/talks/{talk['id']}").json() == talk
    assert client.get("/api/talks?day_id=1").json()["total"] == 10
    filtered = client.get("/api/talks?day_id=2&room_id=3").json()
    assert filtered["total"] == 3
    assert all(t["day_id"] == 2 and t["room"]["id"] == 3 for t in filtered["items"])
    for query in ("day_id=999", "room_id=999", "day_id=999&room_id=1"):
        assert client.get(f"/api/talks?{query}").json() == {"items": [], "total": 0}
    assert "set-cookie" not in client.get("/api/talks").headers


@pytest.mark.parametrize("path", ["/api/talks?day_id=0", "/api/talks?room_id=-1", "/api/talks?day_id=abc", "/api/talks/0", "/api/talks/secret-value"])
def test_validation(client, path):
    response = client.get(path)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert response.json()["error"]["details"]
    assert "secret-value" not in response.text


def test_not_found(client, origin):
    expected = {"error": {"code": "TALK_NOT_FOUND", "message": "Доклад не найден", "details": []}}
    assert client.get("/api/talks/999").json() == expected
    response = client.put(f"{PROGRAM}/talks/999", headers=origin)
    assert response.status_code == 404 and response.json() == expected
    assert response.headers["cache-control"] == "no-store"
    assert "ad_session=" in response.headers["set-cookie"]


def test_program_crud_conflicts(client, origin):
    assert client.get(PROGRAM).json() == dict(talks=[], conflicts=[], selected_count=0, conflicting_talk_count=0)
    assert put(client, 1, origin)["selected_count"] == 1
    assert put(client, 1, origin)["selected_count"] == 1
    for id_ in (2, 3, 4, 5, 11):
        program = put(client, id_, origin)
    assert program["selected_count"] == 6
    assert program["conflicts"] == [
        {"talk_id": 1, "conflicting_talk_ids": [2, 3, 4]},
        {"talk_id": 2, "conflicting_talk_ids": [1, 3, 4]},
        {"talk_id": 3, "conflicting_talk_ids": [1, 2]},
        {"talk_id": 4, "conflicting_talk_ids": [1, 2, 5]},
        {"talk_id": 5, "conflicting_talk_ids": [4]},
    ]
    assert program["conflicting_talk_count"] == 5
    for id_ in (2, 3, 4, 4, 999):
        response = client.delete(f"{PROGRAM}/talks/{id_}", headers=origin)
        assert response.status_code == 204 and response.content == b""
        assert response.headers["cache-control"] == "no-store"
    program = client.get(PROGRAM).json()
    assert program["selected_count"] == 3
    assert program["conflicts"] == [] and program["conflicting_talk_count"] == 0


def test_session_isolation(application, client, origin):
    put(client, 1, origin)
    with TestClient(application) as other:
        assert other.get(PROGRAM + "?session_id=1&token=ignored").json()["talks"] == []
        assert client.cookies.get("ad_session") != other.cookies.get("ad_session")
        put(other, 2, origin)
        other.delete(f"{PROGRAM}/talks/1?session_id=1", headers=origin)
        assert [t["id"] for t in client.get(PROGRAM).json()["talks"]] == [1]
        assert [t["id"] for t in other.get(PROGRAM).json()["talks"]] == [2]


def test_cookie_expiry_and_hash(application, client, origin):
    response = client.get(PROGRAM)
    cookie = response.headers["set-cookie"]
    for expected in ("HttpOnly", "SameSite=lax", "Path=/", "Max-Age=2592000"):
        assert expected in cookie
    assert "Domain=" not in cookie and "Secure" not in cookie
    token = client.cookies.get("ad_session")
    put(client, 1, origin)
    with application.state.sessions() as db:
        stored = db.scalar(select(AnonymousSession).where(AnonymousSession.token_hash == token_hash(token)))
        assert stored.token_hash != token and len(stored.token_hash) == 64
        assert stored.expires_at - stored.created_at == timedelta(days=30)
        original_expiry = stored.expires_at
    assert "set-cookie" not in client.get(PROGRAM).headers
    with application.state.sessions() as db:
        stored = db.scalar(select(AnonymousSession).where(AnonymousSession.token_hash == token_hash(token)))
        assert stored.expires_at == original_expiry
        stored.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        db.commit()
    response = client.get(PROGRAM)
    assert response.json()["selected_count"] == 0
    assert client.cookies.get("ad_session") != token
    client.cookies.clear()
    client.cookies.set("ad_session", "invalid")
    response = client.get(PROGRAM)
    assert response.json()["selected_count"] == 0
    assert "set-cookie" in response.headers


@pytest.mark.parametrize("method", ["put", "delete"])
@pytest.mark.parametrize("value", [None, "https://evil.example", "null", "http://localhost:3000.evil.example"])
def test_origin_denied(client, method, value):
    response = getattr(client, method)(f"{PROGRAM}/talks/1", headers={} if value is None else {"Origin": value})
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "ORIGIN_NOT_ALLOWED"
    assert response.headers["cache-control"] == "no-store"
    assert client.get(PROGRAM).json()["selected_count"] == 0


@pytest.mark.parametrize("method", ["put", "delete"])
def test_mutation_validation(client, origin, method):
    response = getattr(client, method)(f"{PROGRAM}/talks/0", headers=origin)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert response.headers["cache-control"] == "no-store"


def test_delete_initializes_session(client, origin):
    response = client.delete(f"{PROGRAM}/talks/999", headers=origin)
    assert response.status_code == 204
    assert "set-cookie" in response.headers


def test_seed_and_restart(application, client, origin):
    put(client, 1, origin)
    seed(application.state.engine)
    with application.state.sessions() as db:
        assert db.scalar(select(func.count()).select_from(Talk)) == 20
        assert db.scalar(select(func.count()).select_from(SelectedTalk)) == 1
    restarted = create_app(application.state.settings)
    with TestClient(restarted) as second:
        second.cookies.update(client.cookies)
        assert second.get(PROGRAM).json()["selected_count"] == 1
        assert second.get("/api/talks").json()["total"] == 20


def test_concurrent_add(application, client, origin):
    client.get(PROGRAM)
    token = client.cookies.get("ad_session")

    def add(_):
        with TestClient(application) as other:
            other.cookies.set("ad_session", token)
            return other.put(f"{PROGRAM}/talks/1", headers=origin).status_code

    with ThreadPoolExecutor(max_workers=6) as pool:
        assert list(pool.map(add, range(12))) == [200] * 12
    assert client.get(PROGRAM).json()["selected_count"] == 1


@pytest.mark.parametrize("method", ["put", "delete"])
def test_expired_session_on_mutation(application, client, origin, method):
    put(client, 1, origin)
    token = client.cookies.get("ad_session")
    with application.state.sessions.begin() as db:
        old = db.scalar(select(AnonymousSession).where(AnonymousSession.token_hash == token_hash(token)))
        old.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        old_id = old.id
    response = getattr(client, method)(f"{PROGRAM}/talks/2", headers=origin)
    assert response.status_code == (200 if method == "put" else 204)
    assert "set-cookie" in response.headers
    assert client.cookies.get("ad_session") != token
    assert [t["id"] for t in client.get(PROGRAM).json()["talks"]] == ([2] if method == "put" else [])
    with application.state.sessions() as db:
        assert db.scalar(select(SelectedTalk.talk_id).where(SelectedTalk.session_id == old_id)) == 1


def test_body_token_is_not_session_identity(application, client, origin):
    put(client, 1, origin)
    with TestClient(application) as other:
        response = other.put(f"{PROGRAM}/talks/2", headers=origin,
                             json={"token": client.cookies.get("ad_session"), "session_id": 1})
        assert response.status_code == 200
        assert [t["id"] for t in response.json()["talks"]] == [2]
        assert [t["id"] for t in client.get(PROGRAM).json()["talks"]] == [1]
