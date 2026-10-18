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
    assert courses[0]["ext_id"] == "demo-it2271"
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
    # the overview's counters
    course = client.get("/api/courses").json()[0]
    row = next(x for x in course["assignments"] if x["id"] == aid)
    turned_in = sum(r["status"] != "NO_SUBMISSION" for r in subs["rows"])
    assert course["students"] == 11 and row["submissions"] == 11 and row["turned_in"] == turned_in
    assert row["to_review"] == sum(r["needs_review"] and not r["reviewed"] for r in subs["rows"])
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


def test_browsers_always_check_for_a_newer_dashboard(client):
    """After an update the page and its script must change together: a browser that kept an
    old app.js next to a new index.html showed an empty sign-in card."""
    for path in ("/", "/static/app.js", "/static/app.css"):
        r = client.get(path)
        assert r.status_code == 200 and "no-cache" in r.headers.get("cache-control", ""), path
    etag = client.get("/static/app.js").headers["etag"]
    assert client.get("/static/app.js", headers={"If-None-Match": etag}).status_code == 304   # still cheap


def test_classroom_errors_say_what_google_said(monkeypatch):
    """A tool error comes back wrapped in the MCP client's task groups; the teacher must see
    Google's reason (an API switched off), not "cannot reach the Classroom MCP server"."""
    from autograder.clients import ClassroomClient, ServiceError

    async def failing(self, tool, args):
        try:
            raise ServiceError("Classroom: Google Classroom API has not been used in project 3677 before or it is disabled")
        except ServiceError as e:
            raise BaseExceptionGroup("unhandled errors in a TaskGroup", [ExceptionGroup("inner", [e])])
    monkeypatch.setattr(ClassroomClient, "_call", failing)
    with pytest.raises(ServiceError) as err:
        ClassroomClient(url="http://mcp", token="t").courses()
    assert "has not been used in project" in str(err.value) and "cannot reach" not in str(err.value)


def test_teacher_fixes_code_and_it_is_kept(client):
    """The teacher types the right code over a misread answer: it is graded now and on
    every later grading, until they go back to the code from the PDF."""
    login(client)
    client.post("/api/courses/sync")
    aid = client.get("/api/courses").json()[0]["assignments"][0]["id"]
    client.patch(f"/api/assignments/{aid}", json={"time_limit_s": 1.0})
    client.post(f"/api/assignments/{aid}/grade")
    run_jobs(client)
    rows = client.get(f"/api/assignments/{aid}/submissions").json()["rows"]
    details = [client.get(f"/api/submissions/{r['id']}").json() for r in rows if r["status"] == "GRADED"]
    good = next(p for d in details for p in d["programs"] if p["question"] == "1" and p["score"] == 1)
    weak = next(d for d in details if any(p["question"] == "1" and (p["score"] or 0) < 1 for p in d["programs"]))
    before = weak["final_score"]

    assert client.put(f"/api/submissions/{weak['id']}/code", json={"question": "9", "code": "x"}).status_code == 400
    job = client.put(f"/api/submissions/{weak['id']}/code", json={"question": "1", "code": good["code"]}).json()
    assert job["status"] == "queued"
    run_jobs(client)
    d = client.get(f"/api/submissions/{weak['id']}").json()
    q1 = next(p for p in d["programs"] if p["question"] == "1")
    assert q1["fixed"] and q1["score"] == 1 and d["final_score"] > before

    client.post(f"/api/assignments/{aid}/grade")                       # a full re-grade keeps the fix
    run_jobs(client)
    assert next(p for p in client.get(f"/api/submissions/{weak['id']}").json()["programs"]
                if p["question"] == "1")["fixed"]

    client.put(f"/api/submissions/{weak['id']}/code", json={"question": "1", "code": None})
    run_jobs(client)
    d = client.get(f"/api/submissions/{weak['id']}").json()
    assert not any(p["fixed"] for p in d["programs"]) and d["final_score"] == before


def test_student_page_across_assignments(client):
    login(client)
    client.post("/api/courses/sync")
    aid = client.get("/api/courses").json()[0]["assignments"][0]["id"]
    client.patch(f"/api/assignments/{aid}", json={"time_limit_s": 1.0})
    client.post(f"/api/assignments/{aid}/grade")
    run_jobs(client)
    rows = client.get(f"/api/assignments/{aid}/submissions").json()["rows"]
    ananya = next(r for r in rows if r["student"]["name"] == "Ananya Bose")
    d = client.get(f"/api/students/{ananya['student']['id']}").json()
    assert d["student"]["name"] == "Ananya Bose"
    (row,) = d["rows"]
    graded = [r["final_score"] for r in rows if r["status"] == "GRADED"]
    assert row["submission_id"] == ananya["id"] and row["final_score"] == ananya["final_score"]
    assert row["class_avg"] == pytest.approx(sum(graded) / len(graded), abs=0.01)
    assert client.get("/api/students/99999").status_code == 404


def test_similarity_decided_a_group_at_a_time(client):
    login(client)
    client.post("/api/courses/sync")
    aid = client.get("/api/courses").json()[0]["assignments"][0]["id"]
    client.patch(f"/api/assignments/{aid}", json={"time_limit_s": 1.0})
    client.post(f"/api/assignments/{aid}/grade")
    run_jobs(client)
    pairs = client.get(f"/api/assignments/{aid}/similarity").json()
    assert pairs and client.get(f"/api/assignments/{aid}").json()["similar_open"] >= 1
    r = client.post(f"/api/assignments/{aid}/similarity/verdict",
                    json={"ids": [p["id"] for p in pairs], "verdict": "cleared"}).json()
    assert r["changed"] == len(pairs)
    assert {p["verdict"] for p in client.get(f"/api/assignments/{aid}/similarity").json()} == {"cleared"}
    assert client.get(f"/api/assignments/{aid}").json()["similar_open"] == 0
    rows = client.get(f"/api/assignments/{aid}/submissions").json()["rows"]
    assert not any(f["code"] == "SIMILAR_CODE" for r in rows for f in r["flags"])
    assert client.post(f"/api/assignments/{aid}/similarity/verdict",
                       json={"ids": [], "verdict": "maybe"}).status_code == 400
