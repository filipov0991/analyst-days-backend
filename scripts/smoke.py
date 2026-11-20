"""Run against an already started local service; only touches a fresh session."""
import argparse

import httpx

parser = argparse.ArgumentParser()
parser.add_argument("--base-url", default="http://127.0.0.1:8000")
parser.add_argument("--origin", default="http://localhost:3000")
args = parser.parse_args()

with httpx.Client(base_url=args.base_url, timeout=10) as client:
    assert client.get("/api/health").json() == {"status": "ok", "database": "ok"}
    assert client.get("/docs").status_code == 200
    assert len(client.get("/openapi.json").json()["paths"]) == 6
    assert client.get("/api/talks").json()["total"] == 20
    assert client.get("/api/me/program").json()["selected_count"] == 0
    for id_ in (1, 2, 2):
        response = client.put(f"/api/me/program/talks/{id_}", headers={"Origin": args.origin})
        assert response.status_code == 200
    assert response.json()["selected_count"] == 2
    assert response.json()["conflicting_talk_count"] == 2
    response = client.delete("/api/me/program/talks/2", headers={"Origin": args.origin})
    assert response.status_code == 204 and not response.content
    assert client.get("/api/me/program").json()["conflicts"] == []
    assert client.delete("/api/me/program/talks/1", headers={"Origin": args.origin}).status_code == 204
print("Live HTTP smoke passed: health, docs, OpenAPI, 20 talks, session, PUT replay, conflicts, DELETE.")
