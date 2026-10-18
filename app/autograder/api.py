from __future__ import annotations

import csv
import io
import re
import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import FileResponse, RedirectResponse, StreamingResponse
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from pydantic import BaseModel, Field
from sqlalchemy import func, select, text

from . import auth, grading
from .feedback import feedback_text
from .clients import SandboxClient, ServiceError
from .config import settings
from .db import SessionLocal
from .evaluate import MODES
from .models import (Assignment, Course, Job, ProgramResult, Question, SimilarityPair, Student,
                     Submission, TestCase, User)

COOKIE = "ag_session"
MAX_AGE = 12 * 3600


def get_db():
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


# commit before the response is sent, so the next request sees the change
DB = Depends(get_db, scope="function")


def _signer():
    return URLSafeTimedSerializer(settings.secret_key, salt="session")


def signed_in(request: Request, db=DB) -> User:
    """The signed-in teacher, whatever their status (a pending one may only see /me)."""
    tok = request.cookies.get(COOKIE)
    if not tok:
        raise HTTPException(401, "Sign in to continue")
    try:
        uid = _signer().loads(tok, max_age=MAX_AGE).get("uid")
    except (BadSignature, SignatureExpired):
        raise HTTPException(401, "Your session expired. Sign in again.")
    user = db.get(User, uid) if uid else None
    if user is None or user.status == "disabled":
        raise HTTPException(401, "Sign in to continue")
    return user


def require_user(user: User = Depends(signed_in)) -> User:
    if user.status != "active":
        raise HTTPException(403, "An admin has to approve your account first")
    return user


def require_admin(user: User = Depends(require_user)) -> User:
    if not user.is_admin:
        raise HTTPException(403, "Only an admin can do that")
    return user


USER = Depends(require_user)
public = APIRouter(prefix="/api")
api = APIRouter(prefix="/api", dependencies=[USER])
admin = APIRouter(prefix="/api/admin", dependencies=[Depends(require_admin)])

# clients are module attributes so tests can swap them
classroom_client = auth.classroom_for          # (user, course=None) -> that teacher's Classroom
sandbox_client = SandboxClient


# ---------------------------------------------------------------- auth
def _start_session(response: Response, user: User) -> None:
    response.set_cookie(COOKIE, _signer().dumps({"uid": user.id}), max_age=MAX_AGE,
                        httponly=True, samesite="lax", secure=settings.cookie_secure)


def ser_user(u: User) -> dict:
    return {"id": u.id, "email": u.email, "name": u.name, "picture": u.picture, "role": u.role,
            "status": u.status, "google": bool(u.google_token)}


@public.get("/auth/config")
def auth_config():
    """What the sign-in page offers."""
    return {"google": settings.google_login, "local": settings.local_login or not settings.google_login,
            "domain": " or ".join(settings.allowed_domains)}


class Login(BaseModel):
    username: str
    password: str


@public.post("/login")
def login(body: Login, response: Response, db=DB):
    if not (settings.local_login or not settings.google_login):
        raise HTTPException(403, "Sign in with Google")
    ok = (secrets.compare_digest(body.username, settings.admin_user)
          and secrets.compare_digest(body.password, settings.admin_password))
    if not ok:
        raise HTTPException(401, "Wrong username or password")
    user = auth.local_admin(db)
    _start_session(response, user)
    return ser_user(user)


STATE = "ag_oauth_state"


@public.get("/auth/google")
def google_start():
    if not settings.google_login:
        raise HTTPException(404, "Google sign-in isn't set up (GOOGLE_CLIENT_ID in .env)")
    state = secrets.token_urlsafe(24)
    r = RedirectResponse(auth.auth_url(state), status_code=302)
    # lax: the browser must send it back when Google redirects here
    r.set_cookie(STATE, state, max_age=600, httponly=True, samesite="lax", secure=settings.cookie_secure)
    return r


@public.get("/auth/google/callback")
def google_callback(request: Request, db=DB, code: str = "", state: str = "", error: str = ""):
    def back(msg: str = ""):
        from urllib.parse import quote
        r = RedirectResponse("/" + (f"#/signin-error/{quote(msg)}" if msg else ""), status_code=302)
        r.delete_cookie(STATE)
        return r
    if error:
        return back("Google sign-in was cancelled")
    if not state or not secrets.compare_digest(state, request.cookies.get(STATE, "")):
        return back("The sign-in took too long or came from another tab. Try again.")
    try:
        claims, tokens = auth.exchange_code(code)
        user = auth.sign_in_with_google(db, claims, tokens)
    except auth.SignInError as e:
        return back(str(e))
    if user.status == "disabled":
        return back("Your account has been switched off. Ask the admin.")
    r = back()
    _start_session(r, user)
    return r


@public.post("/logout")
def logout(response: Response):
    response.delete_cookie(COOKIE)
    return {"ok": True}


@public.get("/health")
def health(db=DB):
    out = {"app": "ok"}
    try:
        db.execute(text("select 1"))
        out["database"] = "ok"
    except Exception as e:
        out["database"] = f"error: {e}"
    return out


@public.get("/me")
def me(user: User = Depends(signed_in)):
    user.last_seen_at = datetime.now(timezone.utc)
    return ser_user(user)


@api.get("/status")
def status(user: User = USER):
    out = {}
    try:
        out["classroom"] = {"ok": True, **classroom_client(user).info()}
    except Exception as e:
        out["classroom"] = {"ok": False, "error": str(e)}
    try:
        out["sandbox"] = sandbox_client().health()
    except Exception as e:
        out["sandbox"] = {"ok": False, "error": f"cannot reach the sandbox: {e}"}
    return out


# ---------------------------------------------------------------- serializers
def ser_assignment(a: Assignment, db) -> dict:
    counts = dict(db.execute(select(Submission.status, func.count()).where(
        Submission.assignment_id == a.id).group_by(Submission.status)).all())
    review = db.scalar(select(func.count()).where(Submission.assignment_id == a.id,
                                                  Submission.needs_review, ~Submission.reviewed))
    return {"id": a.id, "ext_id": a.ext_id, "course_id": a.course_id, "course_ext_id": a.course.ext_id,
            "title": a.title, "description": a.description,
            "max_points": a.max_points, "due": a.due, "materials": a.materials, "link": a.link,
            "time_limit_s": a.time_limit_s, "compare_mode": a.compare_mode,
            "similarity_threshold": a.similarity_threshold, "starter_code": a.starter_code,
            "tests_imported": a.tests_imported,
            "last_graded_at": a.last_graded_at.isoformat() if a.last_graded_at else None,
            "counts": counts, "to_review": review or 0,
            "n_tests": sum(len(q.tests) for q in a.questions), "n_questions": len(a.questions)}


def ser_question(q: Question) -> dict:
    return {"id": q.id, "label": q.label, "title": q.title, "statement": q.statement, "weight": q.weight,
            "tests": [{"id": t.id, "stdin": t.stdin, "expected": t.expected, "hidden": t.hidden,
                       "weight": t.weight, "source": t.source, "rule": t.rule} for t in q.tests]}


def ser_job(j: Job | None) -> dict | None:
    if not j:
        return None
    return {"id": j.id, "kind": j.kind, "status": j.status, "progress": j.progress, "total": j.total,
            "message": j.message, "created_at": j.created_at.isoformat(),
            "finished_at": j.finished_at.isoformat() if j.finished_at else None}


def ser_sub_row(s: Submission, labels: list[str]) -> dict:
    by_q = {p.question_label: p for p in s.programs}
    strip = []
    for l in labels:
        p = by_q.get(l)
        strip.append({"q": l, "language": p.language if p else None,
                      "compile": p.compile_status if p else "MISSING",
                      "runs": [r.passed for r in p.runs] if p else [],
                      "statuses": [r.status for r in p.runs] if p else []})
    return {"id": s.id, "student": {"id": s.student_id, "name": s.student.name, "email": s.student.email},
            "status": s.status, "state": s.state, "late": s.late, "auto_score": s.auto_score,
            "override_score": s.override_score, "final_score": s.final_score, "flags": s.flags or [],
            "needs_review": s.needs_review, "reviewed": s.reviewed, "strip": strip,
            "published_grade": s.published_grade}


# ---------------------------------------------------------------- courses & assignments
@api.get("/courses")
def courses(db=DB, user: User = USER):
    """The courses this teacher teaches (an admin sees everyone's on the admin page)."""
    aids = [a.id for c in user.courses for a in c.assignments]
    # per assignment: submissions, turned in, waiting for review; per course: students
    counts = {aid: (n, t, r) for aid, n, t, r in db.execute(select(
        Submission.assignment_id, func.count(),
        func.count().filter(Submission.status != "NO_SUBMISSION"),
        func.count().filter(Submission.needs_review, ~Submission.reviewed),
    ).where(Submission.assignment_id.in_(aids)).group_by(Submission.assignment_id)).all()} if aids else {}
    students = dict(db.execute(select(Assignment.course_id, func.count(func.distinct(Submission.student_id)))
                               .join(Submission, Submission.assignment_id == Assignment.id)
                               .where(Assignment.id.in_(aids)).group_by(Assignment.course_id)).all()) if aids else {}
    out = []
    for c in sorted(user.courses, key=lambda c: c.name):
        rows = []
        for a in sorted(c.assignments, key=lambda a: (a.due or "", a.title), reverse=True):
            n, t, r = counts.get(a.id, (0, 0, 0))
            rows.append({"id": a.id, "title": a.title, "due": a.due, "graded": a.last_graded_at is not None,
                         "submissions": n, "turned_in": t, "to_review": r})
        out.append({"id": c.id, "ext_id": c.ext_id, "name": c.name, "section": c.section, "link": c.link,
                    "students": students.get(c.id, 0), "assignments": rows})
    return out


@api.post("/courses/sync")
def sync(db=DB, user: User = USER):
    try:
        n = grading.sync_courses(db, classroom_client(user), user)
    except ServiceError as e:
        raise HTTPException(502, str(e))
    return {"courses": n}


def can_see(user: User, course: Course) -> bool:
    return user.is_admin or user in course.teachers


def _assignment(db, aid, user: User) -> Assignment:
    a = db.get(Assignment, aid)
    if not a or not can_see(user, a.course):     # someone else's: as if it didn't exist
        raise HTTPException(404, "Assignment not found")
    return a


def _owned(obj, assignment: Assignment | None, user: User, what: str):
    if obj is None or assignment is None or not can_see(user, assignment.course):
        raise HTTPException(404, f"{what} not found")
    return obj


@api.get("/assignments/{aid}")
def assignment(aid: int, db=DB, user: User = USER):
    a = _assignment(db, aid, user)
    job = db.scalar(select(Job).where(Job.assignment_id == aid).order_by(Job.id.desc()).limit(1))
    scores = [s.final_score for s in a.submissions if s.final_score is not None and s.status != "NO_SUBMISSION"]
    return {**ser_assignment(a, db), "course": {"id": a.course.id, "name": a.course.name},
            "questions": [ser_question(q) for q in a.questions], "job": ser_job(job),
            "scores": scores}


class AssignmentPatch(BaseModel):
    max_points: float | None = Field(default=None, gt=0, le=1000)
    time_limit_s: float | None = Field(default=None, ge=0.2, le=20)
    compare_mode: str | None = None
    similarity_threshold: float | None = Field(default=None, ge=0.2, le=1.0)
    starter_code: str | None = Field(default=None, max_length=100_000)


@api.patch("/assignments/{aid}")
def patch_assignment(aid: int, body: AssignmentPatch, db=DB, user: User = USER):
    a = _assignment(db, aid, user)
    data = body.model_dump(exclude_none=True)
    if "compare_mode" in data and data["compare_mode"] not in MODES:
        raise HTTPException(400, f"compare_mode must be one of {MODES}")
    for k, v in data.items():
        setattr(a, k, v)
    return ser_assignment(a, db)


@api.post("/assignments/{aid}/import-tests")
def import_tests(aid: int, db=DB, user: User = USER):
    a = _assignment(db, aid, user)
    try:
        return grading.import_tests(db, classroom_client(user, a.course), a)
    except ServiceError as e:
        raise HTTPException(502, str(e))


class ChecksIn(BaseModel):
    pack: str = "oop-assignment-1"


@api.post("/assignments/{aid}/checks")
def add_checks(aid: int, body: ChecksIn, db=DB, user: User = USER):
    """Add requirement checks (see checks.py) to the assignment's questions, by label."""
    from . import checks
    a = _assignment(db, aid, user)
    try:
        n = checks.install(db, a, body.pack)
    except KeyError:
        raise HTTPException(404, f"unknown check pack {body.pack!r}")
    db.commit()
    return {"checks": n, "message": f"Added {n} requirement check(s). They apply the next time you grade."}


class QuestionIn(BaseModel):
    label: str = Field(min_length=1, max_length=32)
    title: str = ""
    statement: str = ""
    weight: float = Field(default=1.0, gt=0, le=100)


@api.post("/assignments/{aid}/questions")
def add_question(aid: int, body: QuestionIn, db=DB, user: User = USER):
    a = _assignment(db, aid, user)
    if any(q.label == body.label for q in a.questions):
        raise HTTPException(409, f"Question {body.label} already exists")
    q = Question(**body.model_dump(), position=len(a.questions))
    a.questions.append(q)
    db.flush()
    return ser_question(q)


class QuestionPatch(BaseModel):
    title: str | None = None
    statement: str | None = None
    weight: float | None = Field(default=None, gt=0, le=100)


@api.patch("/questions/{qid}")
def patch_question(qid: int, body: QuestionPatch, db=DB, user: User = USER):
    q = db.get(Question, qid)
    _owned(q, q and q.assignment, user, "Question")
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(q, k, v)
    return ser_question(q)


@api.delete("/questions/{qid}")
def delete_question(qid: int, db=DB, user: User = USER):
    q = db.get(Question, qid)
    _owned(q, q and q.assignment, user, "Question")
    db.delete(q)
    return {"ok": True}


class TestIn(BaseModel):
    stdin: str = Field(default="", max_length=1_000_000)
    expected: str = Field(default="", max_length=1_000_000)
    hidden: bool = False
    weight: float = Field(default=1.0, gt=0, le=100)


@api.post("/questions/{qid}/tests")
def add_test(qid: int, body: TestIn, db=DB, user: User = USER):
    q = db.get(Question, qid)
    _owned(q, q and q.assignment, user, "Question")
    t = TestCase(**body.model_dump(), source="manual", position=len(q.tests))
    q.tests.append(t)
    db.flush()
    return ser_question(q)


class TestPatch(BaseModel):
    stdin: str | None = Field(default=None, max_length=1_000_000)
    expected: str | None = Field(default=None, max_length=1_000_000)
    hidden: bool | None = None
    weight: float | None = Field(default=None, gt=0, le=100)


@api.patch("/tests/{tid}")
def patch_test(tid: int, body: TestPatch, db=DB, user: User = USER):
    t = db.get(TestCase, tid)
    _owned(t, t and t.question.assignment, user, "Test")
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(t, k, v)
    t.source = "manual"
    return ser_question(t.question)


@api.delete("/tests/{tid}")
def delete_test(tid: int, db=DB, user: User = USER):
    t = db.get(TestCase, tid)
    _owned(t, t and t.question.assignment, user, "Test")
    db.delete(t)
    return {"ok": True}


# ---------------------------------------------------------------- grading jobs
def _active_job(db, aid):
    return db.scalar(select(Job).where(Job.assignment_id == aid, Job.status.in_(["queued", "running"])))


@api.post("/assignments/{aid}/grade")
def grade(aid: int, fresh: bool = False, db=DB, user: User = USER):
    """`fresh`: download every file again, even ones Classroom reports unchanged."""
    _assignment(db, aid, user)
    if j := _active_job(db, aid):
        return ser_job(j)
    j = Job(kind="grade_fresh" if fresh else "grade", assignment_id=aid, user_id=user.id,
            message="Waiting to start")
    db.add(j)
    db.flush()
    return ser_job(j)


@api.post("/submissions/{sid}/regrade")
def regrade(sid: int, db=DB, user: User = USER):
    s = db.get(Submission, sid)
    _owned(s, s and s.assignment, user, "Submission")
    if j := _active_job(db, s.assignment_id):
        return ser_job(j)
    j = Job(kind="grade_one", assignment_id=s.assignment_id, submission_id=sid, user_id=user.id,
            message="Waiting to start")
    db.add(j)
    db.flush()
    return ser_job(j)


class CodeFix(BaseModel):
    question: str = Field(max_length=32)
    code: str | None = Field(default=None, max_length=100_000)   # None: go back to the extracted code


@api.put("/submissions/{sid}/code")
def fix_code(sid: int, body: CodeFix, db=DB, user: User = USER):
    """Correct the code of one question by hand (an OCR misreading, an answer the reader
    missed) and grade the submission again with it."""
    s = db.get(Submission, sid)
    _owned(s, s and s.assignment, user, "Submission")
    if body.question not in {q.label for q in s.assignment.questions}:
        raise HTTPException(400, f"This assignment has no question {body.question}")
    fixes = dict(s.code_fixes or {})
    if body.code is None or not body.code.strip():
        fixes.pop(body.question, None)
    else:
        fixes[body.question] = body.code.replace("\r\n", "\n")
    s.code_fixes = fixes
    if j := _active_job(db, s.assignment_id):
        return ser_job(j)
    j = Job(kind="grade_one", assignment_id=s.assignment_id, submission_id=sid, user_id=user.id,
            message="Waiting to start")
    db.add(j)
    db.flush()
    return ser_job(j)


@api.get("/jobs/{jid}")
def job(jid: int, db=DB, user: User = USER):
    j = db.get(Job, jid)
    _owned(j, j and db.get(Assignment, j.assignment_id), user, "Job")
    return ser_job(j)


# ---------------------------------------------------------------- results
@api.get("/assignments/{aid}/submissions")
def submissions(aid: int, db=DB, user: User = USER):
    a = _assignment(db, aid, user)
    labels = [q.label for q in a.questions] or sorted({p.question_label for s in a.submissions for p in s.programs})
    rows = [ser_sub_row(s, labels) for s in a.submissions]
    rows.sort(key=lambda r: r["student"]["name"].lower())
    return {"labels": labels, "rows": rows}


@api.get("/submissions/{sid}")
def submission(sid: int, db=DB, user: User = USER):
    s = db.get(Submission, sid)
    _owned(s, s and s.assignment, user, "Submission")
    a = s.assignment
    sims = db.scalars(select(SimilarityPair).where((SimilarityPair.sub_a_id == sid) | (SimilarityPair.sub_b_id == sid)))
    siblings = sorted(a.submissions, key=lambda x: x.student.name.lower())
    idx = [x.id for x in siblings].index(s.id)
    return {
        **ser_sub_row(s, [q.label for q in a.questions]),
        "assignment": {"id": a.id, "title": a.title, "max_points": a.max_points},
        "override_note": s.override_note, "error": s.error, "extraction": s.extraction or {},
        "feedback": feedback_text(s),
        "has_pdf": bool(s.pdf_path), "graded_at": s.graded_at.isoformat() if s.graded_at else None,
        "files": [{"title": f.get("title"), "kind": f.get("kind"), "link": f.get("link")}
                  for f in (s.files or []) if f.get("title")],
        "prev_id": siblings[idx - 1].id if idx > 0 else None,
        "next_id": siblings[idx + 1].id if idx + 1 < len(siblings) else None,
        "programs": [{
            "id": p.id, "question": p.question_label, "language": p.language, "code": p.code,
            "claimed_output": p.claimed_output, "repairs": p.repairs, "warnings": p.warnings, "ocr": p.ocr,
            "compile_status": p.compile_status, "compile_output": p.compile_output,
            "tests_passed": p.tests_passed, "tests_total": p.tests_total, "score": p.score,
            "claimed_status": p.claimed_status, "claimed_from_image": bool(p.claimed_from_image),
            "fixed": bool(p.fixed_by_teacher),
            "runs": [{"id": r.id, "stdin": r.stdin, "expected": r.expected, "hidden": r.hidden,
                      "status": r.status, "stdout": r.stdout, "stderr": r.stderr,
                      "exit_code": r.exit_code, "runtime_ms": r.runtime_ms, "passed": r.passed,
                      "rule": r.rule, "note": r.note}
                     for r in p.runs]} for p in s.programs],
        "missing": [q.label for q in a.questions if q.label not in {p.question_label for p in s.programs}],
        "similar": [{"id": p.id, "question": p.question_label, "score": p.score, "verdict": p.verdict,
                     "other": (p.sub_b if p.sub_a_id == sid else p.sub_a).student.name} for p in sims],
    }


def _title_key(title: str):
    """"Assignment 2" before "Assignment 10"; "Assignment 4- 2nd part" after "Assignment 4"."""
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", title.lower())]


@api.get("/students/{stid}")
def student(stid: int, db=DB, user: User = USER):
    """One student across every assignment the teacher can see, next to the class."""
    st = db.get(Student, stid)
    subs = [s for s in db.scalars(select(Submission).where(Submission.student_id == stid))
            if can_see(user, s.assignment.course)] if st else []
    if not subs:
        raise HTTPException(404, "Student not found")
    aids = [s.assignment_id for s in subs]
    avg = dict(db.execute(
        select(Submission.assignment_id,
               func.avg(func.coalesce(Submission.override_score, Submission.auto_score)))
        .where(Submission.assignment_id.in_(aids), Submission.status == "GRADED")
        .group_by(Submission.assignment_id)).all())
    rows = []
    for s in sorted(subs, key=lambda s: (s.assignment.course.name, _title_key(s.assignment.title))):
        a = s.assignment
        rows.append({
            "submission_id": s.id, "course": a.course.name,
            "assignment": {"id": a.id, "title": a.title, "max_points": a.max_points, "due": a.due},
            "status": s.status, "late": s.late, "final_score": s.final_score,
            "needs_review": s.needs_review and not s.reviewed,
            "class_avg": round(avg[a.id], 2) if avg.get(a.id) is not None else None})
    return {"student": {"id": st.id, "name": st.name, "email": st.email}, "rows": rows}


class SubmissionPatch(BaseModel):
    override_score: float | None = None
    clear_override: bool = False
    override_note: str | None = Field(default=None, max_length=5000)
    reviewed: bool | None = None


@api.patch("/submissions/{sid}")
def patch_submission(sid: int, body: SubmissionPatch, db=DB, user: User = USER):
    s = db.get(Submission, sid)
    _owned(s, s and s.assignment, user, "Submission")
    if body.clear_override:
        s.override_score = None
    elif body.override_score is not None:
        if not 0 <= body.override_score <= s.assignment.max_points:
            raise HTTPException(400, f"Score must be between 0 and {s.assignment.max_points:g}")
        s.override_score = body.override_score
    if body.override_note is not None:
        s.override_note = body.override_note
    if body.reviewed is not None:
        s.reviewed = body.reviewed
    return {"final_score": s.final_score, "override_score": s.override_score, "reviewed": s.reviewed}


@api.get("/submissions/{sid}/pdf")
def submission_pdf(sid: int, db=DB, user: User = USER):
    s = db.get(Submission, sid)
    if not s or not s.pdf_path or not can_see(user, s.assignment.course):
        raise HTTPException(404, "No PDF for this submission")
    return FileResponse(s.pdf_path, media_type="application/pdf",
                        headers={"Content-Disposition": "inline"})


# ---------------------------------------------------------------- similarity
@api.get("/assignments/{aid}/similarity")
def similarity(aid: int, db=DB, user: User = USER):
    _assignment(db, aid, user)
    pairs = db.scalars(select(SimilarityPair).where(SimilarityPair.assignment_id == aid)
                       .order_by(SimilarityPair.score.desc()))
    return [{"id": p.id, "question": p.question_label, "score": p.score, "jaccard": p.jaccard,
             "low_confidence": p.low_confidence, "verdict": p.verdict,
             "a": {"id": p.sub_a_id, "name": p.sub_a.student.name},
             "b": {"id": p.sub_b_id, "name": p.sub_b.student.name}} for p in pairs]


def _code_of(sub: Submission, label: str) -> dict:
    p = next((p for p in sub.programs if p.question_label == label), None)
    return {"id": sub.id, "name": sub.student.name, "code": p.code if p else "",
            "language": p.language if p else None}


@api.get("/similarity/{pid}")
def similarity_pair(pid: int, db=DB, user: User = USER):
    p = db.get(SimilarityPair, pid)
    _owned(p, p and p.assignment, user, "Pair")
    return {"id": p.id, "question": p.question_label, "score": p.score, "jaccard": p.jaccard,
            "verdict": p.verdict, "low_confidence": p.low_confidence, "assignment_id": p.assignment_id,
            "a": {**_code_of(p.sub_a, p.question_label), "lines": p.lines_a},
            "b": {**_code_of(p.sub_b, p.question_label), "lines": p.lines_b}}


class Verdict(BaseModel):
    verdict: str


@api.patch("/similarity/{pid}")
def similarity_verdict(pid: int, body: Verdict, db=DB, user: User = USER):
    if body.verdict not in ("", "cleared", "confirmed"):
        raise HTTPException(400, "verdict must be '', 'cleared' or 'confirmed'")
    p = db.get(SimilarityPair, pid)
    _owned(p, p and p.assignment, user, "Pair")
    p.verdict = body.verdict
    grading.run_similarity(db, p.assignment)  # refresh flags
    return {"ok": True}


# ---------------------------------------------------------------- export & publish
@api.get("/assignments/{aid}/export.csv")
def export_csv(aid: int, db=DB, user: User = USER):
    a = _assignment(db, aid, user)
    labels = [q.label for q in a.questions]
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["student", "email", "status", "late"] + [f"Q{l} tests" for l in labels]
               + ["auto_score", "override_score", "final_score", f"out_of", "flags", "note", "feedback"])
    for s in sorted(a.submissions, key=lambda s: s.student.name.lower()):
        by_q = {p.question_label: p for p in s.programs}
        qcols = [f"{by_q[l].tests_passed}/{by_q[l].tests_total}" if l in by_q else "missing" for l in labels]
        w.writerow([s.student.name, s.student.email, s.status, "yes" if s.late else ""] + qcols +
                   [s.auto_score, s.override_score, s.final_score, a.max_points,
                    "; ".join(f["code"] + (f" Q{f['q']}" if f.get("q") else "") for f in s.flags or []),
                    s.override_note, feedback_text(s)])
    name = f"{a.title}.csv".replace("/", "-").replace('"', "")
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": f'attachment; filename="{name}"'})


class Publish(BaseModel):
    assign: bool = False
    only_reviewed: bool = False


@api.post("/assignments/{aid}/publish")
def publish(aid: int, body: Publish, db=DB, user: User = USER):
    a = _assignment(db, aid, user)
    if user not in a.course.teachers:
        raise HTTPException(403, "Only a teacher of this course can publish its grades")
    try:
        cc = classroom_client(user, a.course)
    except ServiceError as e:
        raise HTTPException(502, str(e))
    results = {"published": 0, "skipped": 0, "errors": []}
    for s in a.submissions:
        if s.final_score is None or (body.only_reviewed and s.needs_review and not s.reviewed):
            results["skipped"] += 1
            continue
        try:
            r = cc.set_grade(a.course.ext_id, a.ext_id, s.ext_id, s.final_score, body.assign)
        except ServiceError as e:
            raise HTTPException(502, str(e))
        if r.get("ok"):
            s.published_grade, s.published_at = s.final_score, datetime.now(timezone.utc)
            results["published"] += 1
        else:
            results["errors"].append({"student": s.student.name, "error": r.get("error", "")})
            if "CSV" in r.get("error", ""):  # same answer for every student
                results["errors"][-1]["student"] = "all students"
                break
    return results


# ---------------------------------------------------------------- admin
@admin.get("/users")
def admin_users(db=DB):
    """Every teacher, newest requests first, with how much they've used the app."""
    graded = dict(db.execute(select(Job.user_id, func.count()).where(Job.status == "done")
                             .group_by(Job.user_id)).all())
    users = db.scalars(select(User).order_by((User.status == "pending").desc(), User.created_at.desc())).all()
    return [{**ser_user(u), "courses": len(u.courses), "grading_runs": graded.get(u.id, 0),
             "created_at": u.created_at.isoformat() if u.created_at else None,
             "last_seen_at": u.last_seen_at.isoformat() if u.last_seen_at else None,
             "fixed_admin": u.email in settings.admin_emails or u.email.endswith("@local")} for u in users]


class UserPatch(BaseModel):
    status: str | None = None
    role: str | None = None


@admin.patch("/users/{uid}")
def admin_patch_user(uid: int, body: UserPatch, db=DB, me: User = Depends(require_admin)):
    u = db.get(User, uid)
    if not u:
        raise HTTPException(404, "No such teacher")
    if body.status is not None:
        if body.status not in ("active", "disabled", "pending"):
            raise HTTPException(400, "status must be active, disabled or pending")
        if u.id == me.id and body.status != "active":
            raise HTTPException(400, "You can't switch off your own account")
        u.status = body.status
    if body.role is not None:
        if body.role not in ("teacher", "admin"):
            raise HTTPException(400, "role must be teacher or admin")
        if u.id == me.id and body.role != "admin":
            raise HTTPException(400, "You can't remove your own admin role")
        if u.email in settings.admin_emails and body.role != "admin":
            raise HTTPException(400, f"{u.email} is an admin in ADMIN_EMAILS (.env)")
        u.role = body.role
    return ser_user(u)


@admin.get("/courses")
def admin_courses(db=DB):
    """Every course in the app and who teaches it."""
    out = []
    for c in db.scalars(select(Course).order_by(Course.name)):
        out.append({"id": c.id, "name": c.name, "section": c.section,
                    "teachers": [{"id": t.id, "name": t.name, "email": t.email} for t in c.teachers],
                    "assignments": [{"id": a.id, "title": a.title, "due": a.due,
                                     "graded": a.last_graded_at is not None}
                                    for a in sorted(c.assignments, key=lambda a: (a.due or "", a.title), reverse=True)]})
    return out
