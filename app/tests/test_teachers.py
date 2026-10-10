"""Several teachers, each signing in with their own Google account: who gets in, who sees
what, and whose Google access each Classroom call uses."""
import base64
import json
from urllib.parse import parse_qs, urlparse

import pytest
from conftest import FakeClassroom
from fastapi.testclient import TestClient

ADMIN, ASHA, RAVI = "head@college.ac.in", "asha@college.ac.in", "ravi@college.ac.in"


def id_token(email, name="", verified=True):
    body = base64.urlsafe_b64encode(json.dumps({"email": email, "email_verified": verified,
                                                "name": name or email.split("@")[0]}).encode()).decode()
    return f"x.{body.rstrip('=')}.sig"


@pytest.fixture
def google(app_env, monkeypatch):
    """Google sign-in set up for college.ac.in; Google's token endpoint faked."""
    from autograder import auth, config
    s = config.settings
    for k, v in {"google_client_id": "cid", "google_client_secret": "csecret", "allowed_domain": "college.ac.in",
                 "admin_emails": [ADMIN], "signup": "approve", "local_login": True,
                 "public_url": "https://grader.college.ac.in"}.items():
        monkeypatch.setattr(s, k, v)
    calls = []

    def post_token(data):
        calls.append(data)
        if data["grant_type"] == "authorization_code":
            email = data["code"]                              # the test's "code" is who signs in
            return {"id_token": id_token(email), "refresh_token": f"refresh-{email}", "access_token": "a",
                    "scope": " ".join(auth.SCOPES)}
        if data["refresh_token"] == "refresh-revoked":
            raise auth.SignInError("invalid_grant")
        return {"access_token": "access-for-" + data["refresh_token"][8:], "expires_in": 3600}
    monkeypatch.setattr(auth, "_post_token", post_token)
    auth._cache.clear()
    return calls


class PerTeacherClassroom(FakeClassroom):
    """The demo course belongs to Asha's Classroom only; records whose access was used."""
    used = []

    def __init__(self, user=None, course=None):
        super().__init__()
        self.user = user
        PerTeacherClassroom.used.append(user.email if user else None)

    def courses(self):
        return super().courses() if self.user and self.user.email in (ASHA, "ta@local") else []


@pytest.fixture
def app(google, monkeypatch):
    from autograder import api
    monkeypatch.setattr(api, "classroom_client", PerTeacherClassroom)
    PerTeacherClassroom.used = []
    from autograder.main import create_app
    return create_app(start_worker=False)


def browser(app):
    return TestClient(app, base_url="https://grader.college.ac.in")


def sign_in(c, email):
    r = c.get("/api/auth/google", follow_redirects=False)
    assert r.status_code == 302
    state = parse_qs(urlparse(r.headers["location"]).query)["state"][0]
    return c.get(f"/api/auth/google/callback?code={email}&state={state}", follow_redirects=False)


def test_google_sign_in_page_asks_only_for_college_accounts(app):
    with browser(app) as c:
        assert c.get("/api/auth/config").json() == {"google": True, "local": True, "domain": "college.ac.in"}
        q = parse_qs(urlparse(c.get("/api/auth/google", follow_redirects=False).headers["location"]).query)
        assert q["hd"] == ["college.ac.in"] and q["access_type"] == ["offline"]
        assert q["redirect_uri"] == ["https://grader.college.ac.in/api/auth/google/callback"]
        assert "https://www.googleapis.com/auth/classroom.coursework.students" in q["scope"][0]


def test_admin_from_env_gets_in_and_the_grant_is_kept_encrypted(app):
    from autograder.db import session_scope
    from autograder.models import User
    with browser(app) as c:
        r = sign_in(c, ADMIN)
        assert r.status_code == 302 and r.headers["location"] == "/"
        me = c.get("/api/me").json()
        assert me["role"] == "admin" and me["status"] == "active" and me["google"]
    with session_scope() as db:
        u = db.query(User).filter_by(email=ADMIN).one()
        assert u.google_token and "refresh-" not in u.google_token


def test_other_domains_and_forged_callbacks_are_refused(app):
    with browser(app) as c:
        r = sign_in(c, "someone@gmail.com")
        assert "signin-error" in r.headers["location"] and c.get("/api/me").status_code == 401
        r = c.get(f"/api/auth/google/callback?code={ASHA}&state=forged", follow_redirects=False)
        assert "signin-error" in r.headers["location"] and c.get("/api/me").status_code == 401


def test_a_new_teacher_waits_for_the_admin(app):
    with browser(app) as admin, browser(app) as asha:
        sign_in(asha, ASHA)
        assert asha.get("/api/me").json()["status"] == "pending"
        assert asha.get("/api/courses").status_code == 403
        sign_in(admin, ADMIN)
        users = admin.get("/api/admin/users").json()
        pending = next(u for u in users if u["email"] == ASHA)
        assert users[0]["email"] == ASHA                     # requests waiting come first
        assert admin.patch(f"/api/admin/users/{pending['id']}", json={"status": "active"}).status_code == 200
        assert asha.get("/api/courses").status_code == 200
        assert asha.get("/api/admin/users").status_code == 403         # a teacher isn't an admin
        admin.patch(f"/api/admin/users/{pending['id']}", json={"status": "disabled"})
        assert asha.get("/api/courses").status_code == 401             # switched off: signed out


def test_the_admin_cannot_lock_themselves_out(app):
    with browser(app) as c:
        sign_in(c, ADMIN)
        me = c.get("/api/me").json()
        assert c.patch(f"/api/admin/users/{me['id']}", json={"status": "disabled"}).status_code == 400
        assert c.patch(f"/api/admin/users/{me['id']}", json={"role": "teacher"}).status_code == 400


def approve(admin, email):
    uid = next(u["id"] for u in admin.get("/api/admin/users").json() if u["email"] == email)
    admin.patch(f"/api/admin/users/{uid}", json={"status": "active"})


def test_teachers_see_only_their_own_courses(app):
    with browser(app) as admin, browser(app) as asha, browser(app) as ravi:
        sign_in(admin, ADMIN)
        for t, email in ((asha, ASHA), (ravi, RAVI)):
            sign_in(t, email)
            approve(admin, email)
        assert asha.post("/api/courses/sync").json() == {"courses": 1}
        assert ravi.post("/api/courses/sync").json() == {"courses": 0}
        aid = asha.get("/api/courses").json()[0]["assignments"][0]["id"]
        assert ravi.get("/api/courses").json() == []
        # Ravi can't reach Asha's assignment, its questions, jobs, results or grades by id
        assert ravi.get(f"/api/assignments/{aid}").status_code == 404
        assert ravi.post(f"/api/assignments/{aid}/grade").status_code == 404
        assert ravi.get(f"/api/assignments/{aid}/export.csv").status_code == 404
        job = asha.post(f"/api/assignments/{aid}/grade").json()
        assert ravi.get(f"/api/jobs/{job['id']}").status_code == 404
        q = asha.post(f"/api/assignments/{aid}/questions", json={"label": "9"}).json()
        assert ravi.post(f"/api/questions/{q['id']}/tests", json={"expected": "x"}).status_code == 404
        assert ravi.delete(f"/api/questions/{q['id']}").status_code == 404
        # the admin can look at everything, but only the course's teacher publishes grades
        assert admin.get(f"/api/assignments/{aid}").status_code == 200
        courses = admin.get("/api/admin/courses").json()
        assert [t["email"] for t in courses[0]["teachers"]] == [ASHA]
        assert admin.post(f"/api/assignments/{aid}/publish", json={}).status_code == 403


def test_grading_reads_classroom_as_the_teacher_who_started_it(app):
    with browser(app) as admin, browser(app) as asha:
        sign_in(admin, ADMIN)
        sign_in(asha, ASHA)
        approve(admin, ASHA)
        asha.post("/api/courses/sync")
        aid = asha.get("/api/courses").json()[0]["assignments"][0]["id"]
        asha.post(f"/api/assignments/{aid}/grade")
        PerTeacherClassroom.used = []
        while app.state.worker.run_once():
            pass
        assert PerTeacherClassroom.used == [ASHA]
        assert asha.get(f"/api/assignments/{aid}").json()["job"]["status"] == "done"


def test_courses_from_before_accounts_go_to_the_first_admin(app_env):
    from autograder.main import create_app
    from autograder import api
    app = create_app(start_worker=False)
    with TestClient(app) as c:
        c.post("/api/login", json={"username": "ta", "password": "pw"})
        assert c.post("/api/courses/sync").json() == {"courses": 1}
        assert len(c.get("/api/courses").json()) == 1


def test_access_tokens_come_from_each_teachers_grant(google):
    from autograder import auth
    from autograder.clients import ServiceError
    from autograder.models import Course, User
    asha = User(id=1, email=ASHA, google_token=auth.seal(f"refresh-{ASHA}"), role="teacher", status="active")
    head = User(id=2, email=ADMIN, google_token="", role="admin", status="active")
    assert auth.classroom_for(asha).access_token == f"access-for-{ASHA}"
    auth.classroom_for(asha)
    assert sum(c["grant_type"] == "refresh_token" for c in google) == 1        # cached for the hour
    # the admin opening Asha's course reads it with Asha's access
    course = Course(ext_id="c", name="c", teachers=[asha])
    assert auth.classroom_for(head, course).access_token == f"access-for-{ASHA}"
    # a teacher without a grant is told to sign in again
    with pytest.raises(ServiceError, match="sign in"):
        auth.classroom_for(User(id=3, email=RAVI, google_token="", role="teacher"))
    revoked = User(id=4, email="x@college.ac.in", google_token=auth.seal("refresh-revoked"), role="teacher")
    with pytest.raises(ServiceError, match="sign in again"):
        auth.classroom_for(revoked)


def test_local_form_can_be_switched_off(app, monkeypatch):
    from autograder import config
    monkeypatch.setattr(config.settings, "local_login", False)
    with browser(app) as c:
        assert c.get("/api/auth/config").json()["local"] is False
        assert c.post("/api/login", json={"username": "ta", "password": "pw"}).status_code == 403
