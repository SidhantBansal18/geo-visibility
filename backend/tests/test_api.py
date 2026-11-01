import os
import time

os.environ["GEO_MOCK"] = "1"
os.environ["SCHEDULER_ENABLED"] = "0"
os.environ["DATABASE_URL"] = "sqlite:////tmp/geo_test_api.db"
if os.path.exists("/tmp/geo_test_api.db"):
    os.remove("/tmp/geo_test_api.db")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

QUERIES = [{"text": "best LED wall rental in Dallas, TX", "kind": "unbranded"},
           {"text": "LED wall rental for a wedding in Dallas", "kind": "use_case"},
           {"text": "Is BrightWave LED any good?", "kind": "branded"}]


def _wait(c, rid):
    for _ in range(200):
        run = c.get(f"/api/runs/{rid}").json()
        if run["status"] in ("done", "failed"):
            return run
        time.sleep(0.05)
    raise AssertionError("run did not finish")


def test_full_flow_mock():
    with TestClient(app) as c:
        assert c.get("/api/health").json()["mock"] is True
        r = c.post("/api/businesses", json={
            "url": "brightwaveled.com", "name": "BrightWave LED", "category": "LED wall rental",
            "location": "Dallas, TX", "queries": QUERIES, "samples_per_query": 2,
        })
        assert r.status_code == 201
        b = r.json()
        run = _wait(c, b["run_id"])
        assert run["status"] == "done", run["error"]
        assert run["progress_done"] == run["progress_total"] == 3 * 3 * 2
        assert run["summary"]["overall"]["visibility"] is not None
        assert run["competitors"] and run["source_gaps"] and run["recommendations"]

        # Conflict while a run is active, then a second run for the trend.
        r2 = c.post(f"/api/businesses/{b['id']}/runs", json={"samples_per_query": 1})
        assert r2.status_code == 202
        assert c.post(f"/api/businesses/{b['id']}/runs").status_code == 409
        _wait(c, r2.json()["id"])
        assert len(c.get(f"/api/businesses/{b['id']}/runs").json()) == 2

        resp = c.get(f"/api/runs/{b['run_id']}/responses", params={"engine": "gemini"}).json()
        assert resp and all(x["engine"] == "gemini" for x in resp)

        qs = c.put(f"/api/businesses/{b['id']}/queries", json=[{"text": "new query in Dallas", "kind": "unbranded"}]).json()
        assert len(qs) == 1

        rec = run["recommendations"][0]
        assert c.patch(f"/api/recommendations/{rec['id']}", json={"done": True}).json()["done"] is True
        assert c.delete(f"/api/businesses/{b['id']}").status_code == 204
