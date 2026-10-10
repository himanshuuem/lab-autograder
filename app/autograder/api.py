from __future__ import annotations

import csv
import io
import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import FileResponse, StreamingResponse
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from pydantic import BaseModel, Field
from sqlalchemy import func, select, text

from . import grading
from .clients import ClassroomClient, SandboxClient, ServiceError
from .config import settings
from .db import SessionLocal
from .evaluate import MODES
from .models import (Assignment, Course, Job, ProgramResult, Question, SimilarityPair, Submission,
                     TestCase)

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


def require_user(request: Request) -> str:
    tok = request.cookies.get(COOKIE)
    if not tok:
        raise HTTPException(401, "Sign in to continue")
    try:
        return _signer().loads(tok, max_age=MAX_AGE)["u"]
    except (BadSignature, SignatureExpired):
        raise HTTPException(401, "Your session expired. Sign in again.")


public = APIRouter(prefix="/api")
api = APIRouter(prefix="/api", dependencies=[Depends(require_user)])

# clients are module attributes so tests can swap them
classroom_client = ClassroomClient
sandbox_client = SandboxClient


# ---------------------------------------------------------------- auth
class Login(BaseModel):
    username: str
    password: str


@public.post("/login")
def login(body: Login, response: Response):
    ok = (secrets.compare_digest(body.username, settings.admin_user)
          and secrets.compare_digest(body.password, settings.admin_password))
    if not ok:
        raise HTTPException(401, "Wrong username or password")
    response.set_cookie(COOKIE, _signer().dumps({"u": body.username}), max_age=MAX_AGE,
                        httponly=True, samesite="strict", secure=settings.cookie_secure)
    return {"user": body.username}


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


@api.get("/me")
def me(user: str = Depends(require_user)):
    return {"user": user}


@api.get("/status")
def status():
    out = {}
    try:
        out["classroom"] = {"ok": True, **classroom_client().info()}
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
    return {"id": s.id, "student": {"name": s.student.name, "email": s.student.email},
            "status": s.status, "state": s.state, "late": s.late, "auto_score": s.auto_score,
            "override_score": s.override_score, "final_score": s.final_score, "flags": s.flags or [],
            "needs_review": s.needs_review, "reviewed": s.reviewed, "strip": strip,
            "published_grade": s.published_grade}


# ---------------------------------------------------------------- courses & assignments
@api.get("/courses")
def courses(db=DB):
    out = []
    for c in db.scalars(select(Course).order_by(Course.name)):
        out.append({"id": c.id, "name": c.name, "section": c.section, "link": c.link,
                    "assignments": [{"id": a.id, "title": a.title, "due": a.due,
                                     "graded": a.last_graded_at is not None}
                                    for a in sorted(c.assignments, key=lambda a: (a.due or "", a.title), reverse=True)]})
    return out


@api.post("/courses/sync")
def sync(db=DB):
    try:
        n = grading.sync_courses(db, classroom_client())
    except ServiceError as e:
        raise HTTPException(502, str(e))
    return {"courses": n}


def _assignment(db, aid) -> Assignment:
    a = db.get(Assignment, aid)
    if not a:
        raise HTTPException(404, "Assignment not found")
    return a


@api.get("/assignments/{aid}")
def assignment(aid: int, db=DB):
    a = _assignment(db, aid)
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
def patch_assignment(aid: int, body: AssignmentPatch, db=DB):
    a = _assignment(db, aid)
    data = body.model_dump(exclude_none=True)
    if "compare_mode" in data and data["compare_mode"] not in MODES:
        raise HTTPException(400, f"compare_mode must be one of {MODES}")
    for k, v in data.items():
        setattr(a, k, v)
    return ser_assignment(a, db)


@api.post("/assignments/{aid}/import-tests")
def import_tests(aid: int, db=DB):
    a = _assignment(db, aid)
    try:
        return grading.import_tests(db, classroom_client(), a)
    except ServiceError as e:
        raise HTTPException(502, str(e))


class ChecksIn(BaseModel):
    pack: str = "oop-assignment-1"


@api.post("/assignments/{aid}/checks")
def add_checks(aid: int, body: ChecksIn, db=DB):
    """Add requirement checks (see checks.py) to the assignment's questions, by label."""
    from . import checks
    a = _assignment(db, aid)
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
def add_question(aid: int, body: QuestionIn, db=DB):
    a = _assignment(db, aid)
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
def patch_question(qid: int, body: QuestionPatch, db=DB):
    q = db.get(Question, qid)
    if not q:
        raise HTTPException(404, "Question not found")
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(q, k, v)
    return ser_question(q)


@api.delete("/questions/{qid}")
def delete_question(qid: int, db=DB):
    q = db.get(Question, qid)
    if not q:
        raise HTTPException(404, "Question not found")
    db.delete(q)
    return {"ok": True}


class TestIn(BaseModel):
    stdin: str = Field(default="", max_length=1_000_000)
    expected: str = Field(default="", max_length=1_000_000)
    hidden: bool = False
    weight: float = Field(default=1.0, gt=0, le=100)


@api.post("/questions/{qid}/tests")
def add_test(qid: int, body: TestIn, db=DB):
    q = db.get(Question, qid)
    if not q:
        raise HTTPException(404, "Question not found")
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
def patch_test(tid: int, body: TestPatch, db=DB):
    t = db.get(TestCase, tid)
    if not t:
        raise HTTPException(404, "Test not found")
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(t, k, v)
    t.source = "manual"
    return ser_question(t.question)


@api.delete("/tests/{tid}")
def delete_test(tid: int, db=DB):
    t = db.get(TestCase, tid)
    if not t:
        raise HTTPException(404, "Test not found")
    db.delete(t)
    return {"ok": True}


# ---------------------------------------------------------------- grading jobs
def _active_job(db, aid):
    return db.scalar(select(Job).where(Job.assignment_id == aid, Job.status.in_(["queued", "running"])))


@api.post("/assignments/{aid}/grade")
def grade(aid: int, db=DB):
    _assignment(db, aid)
    if j := _active_job(db, aid):
        return ser_job(j)
    j = Job(kind="grade", assignment_id=aid, message="Waiting to start")
    db.add(j)
    db.flush()
    return ser_job(j)


@api.post("/submissions/{sid}/regrade")
def regrade(sid: int, db=DB):
    s = db.get(Submission, sid)
    if not s:
        raise HTTPException(404, "Submission not found")
    if j := _active_job(db, s.assignment_id):
        return ser_job(j)
    j = Job(kind="grade_one", assignment_id=s.assignment_id, submission_id=sid, message="Waiting to start")
    db.add(j)
    db.flush()
    return ser_job(j)


@api.get("/jobs/{jid}")
def job(jid: int, db=DB):
    j = db.get(Job, jid)
    if not j:
        raise HTTPException(404, "Job not found")
    return ser_job(j)


# ---------------------------------------------------------------- results
@api.get("/assignments/{aid}/submissions")
def submissions(aid: int, db=DB):
    a = _assignment(db, aid)
    labels = [q.label for q in a.questions] or sorted({p.question_label for s in a.submissions for p in s.programs})
    rows = [ser_sub_row(s, labels) for s in a.submissions]
    rows.sort(key=lambda r: r["student"]["name"].lower())
    return {"labels": labels, "rows": rows}


@api.get("/submissions/{sid}")
def submission(sid: int, db=DB):
    s = db.get(Submission, sid)
    if not s:
        raise HTTPException(404, "Submission not found")
    a = s.assignment
    sims = db.scalars(select(SimilarityPair).where((SimilarityPair.sub_a_id == sid) | (SimilarityPair.sub_b_id == sid)))
    siblings = sorted(a.submissions, key=lambda x: x.student.name.lower())
    idx = [x.id for x in siblings].index(s.id)
    return {
        **ser_sub_row(s, [q.label for q in a.questions]),
        "assignment": {"id": a.id, "title": a.title, "max_points": a.max_points},
        "override_note": s.override_note, "error": s.error, "extraction": s.extraction or {},
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
            "runs": [{"id": r.id, "stdin": r.stdin, "expected": r.expected, "hidden": r.hidden,
                      "status": r.status, "stdout": r.stdout, "stderr": r.stderr,
                      "exit_code": r.exit_code, "runtime_ms": r.runtime_ms, "passed": r.passed,
                      "rule": r.rule, "note": r.note}
                     for r in p.runs]} for p in s.programs],
        "similar": [{"id": p.id, "question": p.question_label, "score": p.score, "verdict": p.verdict,
                     "other": (p.sub_b if p.sub_a_id == sid else p.sub_a).student.name} for p in sims],
    }


class SubmissionPatch(BaseModel):
    override_score: float | None = None
    clear_override: bool = False
    override_note: str | None = Field(default=None, max_length=5000)
    reviewed: bool | None = None


@api.patch("/submissions/{sid}")
def patch_submission(sid: int, body: SubmissionPatch, db=DB):
    s = db.get(Submission, sid)
    if not s:
        raise HTTPException(404, "Submission not found")
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
def submission_pdf(sid: int, db=DB):
    s = db.get(Submission, sid)
    if not s or not s.pdf_path:
        raise HTTPException(404, "No PDF for this submission")
    return FileResponse(s.pdf_path, media_type="application/pdf",
                        headers={"Content-Disposition": "inline"})


# ---------------------------------------------------------------- similarity
@api.get("/assignments/{aid}/similarity")
def similarity(aid: int, db=DB):
    _assignment(db, aid)
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
def similarity_pair(pid: int, db=DB):
    p = db.get(SimilarityPair, pid)
    if not p:
        raise HTTPException(404, "Pair not found")
    return {"id": p.id, "question": p.question_label, "score": p.score, "jaccard": p.jaccard,
            "verdict": p.verdict, "low_confidence": p.low_confidence, "assignment_id": p.assignment_id,
            "a": {**_code_of(p.sub_a, p.question_label), "lines": p.lines_a},
            "b": {**_code_of(p.sub_b, p.question_label), "lines": p.lines_b}}


class Verdict(BaseModel):
    verdict: str


@api.patch("/similarity/{pid}")
def similarity_verdict(pid: int, body: Verdict, db=DB):
    if body.verdict not in ("", "cleared", "confirmed"):
        raise HTTPException(400, "verdict must be '', 'cleared' or 'confirmed'")
    p = db.get(SimilarityPair, pid)
    if not p:
        raise HTTPException(404, "Pair not found")
    p.verdict = body.verdict
    grading.run_similarity(db, p.assignment)  # refresh flags
    return {"ok": True}


# ---------------------------------------------------------------- export & publish
@api.get("/assignments/{aid}/export.csv")
def export_csv(aid: int, db=DB):
    a = _assignment(db, aid)
    labels = [q.label for q in a.questions]
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["student", "email", "status", "late"] + [f"Q{l} tests" for l in labels]
               + ["auto_score", "override_score", "final_score", f"out_of", "flags", "note"])
    for s in sorted(a.submissions, key=lambda s: s.student.name.lower()):
        by_q = {p.question_label: p for p in s.programs}
        qcols = [f"{by_q[l].tests_passed}/{by_q[l].tests_total}" if l in by_q else "missing" for l in labels]
        w.writerow([s.student.name, s.student.email, s.status, "yes" if s.late else ""] + qcols +
                   [s.auto_score, s.override_score, s.final_score, a.max_points,
                    "; ".join(f["code"] + (f" Q{f['q']}" if f.get("q") else "") for f in s.flags or []),
                    s.override_note])
    name = f"{a.title}.csv".replace("/", "-").replace('"', "")
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": f'attachment; filename="{name}"'})


class Publish(BaseModel):
    assign: bool = False
    only_reviewed: bool = False


@api.post("/assignments/{aid}/publish")
def publish(aid: int, body: Publish, db=DB):
    a = _assignment(db, aid)
    cc = classroom_client()
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
