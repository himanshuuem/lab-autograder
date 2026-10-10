import pytest
from conftest import FakeClassroom
from fastapi.testclient import TestClient


@pytest.fixture
def client(app_env):
    from autograder.main import create_app
    app = create_app(start_worker=False)
    with TestClient(app) as c:
        c.app_ref = app
        yield c


def login(c):
    r = c.post("/api/login", json={"username": "ta", "password": "pw"})
    assert r.status_code == 200


def run_jobs(c):
    while c.app_ref.state.worker.run_once():
        pass


def test_auth(client):
    assert client.get("/api/courses").status_code == 401
    assert client.post("/api/login", json={"username": "ta", "password": "nope"}).status_code == 401
    login(client)
    me = client.get("/api/me").json()
    assert me["email"] == "ta@local" and me["role"] == "admin" and me["status"] == "active"
    client.post("/api/logout")
    assert client.get("/api/courses").status_code == 401


def test_tampered_cookie_rejected(client):
    client.cookies.set("ag_session", "forged.value.here")
    assert client.get("/api/courses").status_code == 401


def test_dashboard_served(client):
    r = client.get("/")
    assert r.status_code == 200 and "Lab Grader" in r.text
    assert client.get("/static/app.js").status_code == 200
    assert client.get("/api/health").json()["database"] == "ok"


def test_full_flow(client):
    login(client)
    assert client.post("/api/courses/sync").json() == {"courses": 1}
    courses = client.get("/api/courses").json()
    aid = courses[0]["assignments"][0]["id"]

    r = client.post(f"/api/assignments/{aid}/import-tests").json()
    assert r["questions"] == 2 and r["tests"] == 3
    a = client.get(f"/api/assignments/{aid}").json()
    q1 = a["questions"][0]
    # add a hidden test, then edit and delete a scratch one
    client.post(f"/api/questions/{q1['id']}/tests", json={"stdin": "1\n7\n", "expected": "7", "hidden": True})
    scratch = client.post(f"/api/questions/{q1['id']}/tests", json={"stdin": "x", "expected": "y"}).json()["tests"][-1]
    assert client.patch(f"/api/tests/{scratch['id']}", json={"expected": "z"}).json()["tests"][-1]["expected"] == "z"
    assert client.delete(f"/api/tests/{scratch['id']}").status_code == 200
    assert client.patch(f"/api/assignments/{aid}", json={"time_limit_s": 1.0}).status_code == 200
    assert client.patch(f"/api/assignments/{aid}", json={"compare_mode": "fuzzy"}).status_code == 400

    job = client.post(f"/api/assignments/{aid}/grade").json()
    assert job["status"] == "queued"
    assert client.post(f"/api/assignments/{aid}/grade").json()["id"] == job["id"]  # no duplicates
    run_jobs(client)
    assert client.get(f"/api/jobs/{job['id']}").json()["status"] == "done"

    subs = client.get(f"/api/assignments/{aid}/submissions").json()
    assert subs["labels"] == ["1", "2"] and len(subs["rows"]) == 11
    ananya = next(r for r in subs["rows"] if r["student"]["name"] == "Ananya Bose")
    assert ananya["final_score"] == 20
    assert ananya["strip"][0]["runs"] == [True, True, True]   # 2 sample + 1 hidden

    riya = next(r for r in subs["rows"] if r["student"]["name"] == "Riya Sen")
    rd = client.get(f"/api/submissions/{riya['id']}").json()
    assert rd["files"] == [{"title": "Riya_Sen_Lab3.docx", "kind": "office", "link": ""}]
    assert all(p["claimed_from_image"] for p in rd["programs"])
    assert client.get(f"/api/submissions/{riya['id']}/pdf").content.startswith(b"%PDF")

    detail = client.get(f"/api/submissions/{ananya['id']}").json()
    assert detail["programs"][0]["runs"][2]["hidden"] is True
    assert detail["has_pdf"] and client.get(f"/api/submissions/{ananya['id']}/pdf").content.startswith(b"%PDF")
    assert detail["similar"] and detail["next_id"]

    # override and review
    assert client.patch(f"/api/submissions/{ananya['id']}", json={"override_score": 99}).status_code == 400
    r = client.patch(f"/api/submissions/{ananya['id']}", json={"override_score": 18.5, "override_note": "copied", "reviewed": True}).json()
    assert r["final_score"] == 18.5 and r["reviewed"]

    # similarity
    pairs = client.get(f"/api/assignments/{aid}/similarity").json()
    assert pairs and pairs[0]["score"] >= 0.9
    pair = client.get(f"/api/similarity/{pairs[0]['id']}").json()
    assert pair["a"]["code"] and pair["a"]["lines"]
    client.patch(f"/api/similarity/{pairs[0]['id']}", json={"verdict": "confirmed"})
    assert client.get(f"/api/similarity/{pairs[0]['id']}").json()["verdict"] == "confirmed"

    # CSV
    csv = client.get(f"/api/assignments/{aid}/export.csv")
    assert csv.headers["content-type"].startswith("text/csv")
    assert "Ananya Bose" in csv.text and "18.5" in csv.text and "NOT_SUBMITTED" in csv.text

    # publish
    r = client.post(f"/api/assignments/{aid}/publish", json={"assign": True}).json()
    assert r["published"] == 11 and not r["errors"]
    assert FakeClassroom.provider.grades["sub-s01"] == {"draft": 18.5, "assigned": 18.5}


def test_publish_403_explained(client):
    login(client)
    client.post("/api/courses/sync")
    aid = client.get("/api/courses").json()[0]["assignments"][0]["id"]
    client.post(f"/api/assignments/{aid}/grade")
    run_jobs(client)
    FakeClassroom.fail_grades_403 = True
    r = client.post(f"/api/assignments/{aid}/publish", json={}).json()
    assert r["published"] == 0 and r["errors"][0]["student"] == "all students"


def test_questions_crud_and_404s(client):
    login(client)
    client.post("/api/courses/sync")
    aid = client.get("/api/courses").json()[0]["assignments"][0]["id"]
    q = client.post(f"/api/assignments/{aid}/questions", json={"label": "3", "title": "Extra"}).json()
    assert client.post(f"/api/assignments/{aid}/questions", json={"label": "3"}).status_code == 409
    assert client.patch(f"/api/questions/{q['id']}", json={"weight": 2}).json()["weight"] == 2
    assert client.delete(f"/api/questions/{q['id']}").status_code == 200
    for url in ("/api/assignments/999", "/api/submissions/999", "/api/similarity/999", "/api/jobs/999"):
        assert client.get(url).status_code == 404


def test_status(client):
    login(client)
    s = client.get("/api/status").json()
    assert s["classroom"]["ok"] and s["sandbox"]["ok"]
