"""Check a change to the extractor or the grader against every real submission already
downloaded, before re-grading anything for real.

  python -m autograder.regress save  [--assignment ID]   remember today's scores
  python -m autograder.regress check [--assignment ID]   grade again without saving, list what moved

The baseline lives in DATA_DIR/regress/ (with the submissions, never in git: the PDFs and
names are the students'). `check` exits 1 when any score went down, so it can gate a deploy.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import select

from .clients import SandboxClient
from .config import settings
from .db import SessionLocal, init_engine
from .grading import grade_submission
from .models import Submission


def _path() -> str:
    return os.path.join(settings.data_dir, "regress", "baseline.json")


def _snapshot(sub: Submission) -> dict:
    return {"score": sub.auto_score, "status": sub.status,
            "q": {p.question_label: p.score for p in sub.programs}}


def _ids(assignment: int | None) -> list[int]:
    db = SessionLocal()
    try:
        q = select(Submission.id).order_by(Submission.id)
        if assignment:
            q = q.where(Submission.assignment_id == assignment)
        return list(db.scalars(q))
    finally:
        db.close()


def _current(sid: int) -> dict:
    db = SessionLocal()
    try:
        return _snapshot(db.get(Submission, sid))
    finally:
        db.close()


def _dry_grade(sid: int, sb: SandboxClient) -> tuple[dict, str]:
    """Grade one submission in a transaction that is rolled back: nothing is saved."""
    db = SessionLocal()
    try:
        sub = db.get(Submission, sid)
        who = f"{sub.assignment.title} / {sub.student.name}"
        grade_submission(db, sb, sub)
        db.flush()
        return _snapshot(sub), who
    finally:
        db.rollback()
        db.close()


def save(assignment: int | None) -> int:
    ids = _ids(assignment)
    base = {}
    if assignment and os.path.exists(_path()):
        base = json.load(open(_path()))
    base.update({str(i): _current(i) for i in ids})
    os.makedirs(os.path.dirname(_path()), exist_ok=True)
    with open(_path(), "w") as f:
        json.dump(base, f)
    print(f"Saved the scores of {len(ids)} submission(s) to {_path()}")
    return 0


def check(assignment: int | None, workers: int, sb=None) -> int:
    if not os.path.exists(_path()):
        print("No baseline yet: run `python -m autograder.regress save` first.")
        return 2
    base = json.load(open(_path()))
    ids = [i for i in _ids(assignment) if str(i) in base]
    sb = sb or SandboxClient()
    done = [0]

    def one(sid):
        r = _dry_grade(sid, sb)
        done[0] += 1
        if done[0] % 25 == 0:
            print(f"  {done[0]}/{len(ids)}", file=sys.stderr)
        return sid, r

    with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
        results = list(ex.map(one, ids))
    up, down = [], []
    for sid, (now, who) in results:
        was = base[str(sid)]
        a, b = was["score"] or 0, now["score"] or 0
        if abs(a - b) < 0.005 and was["status"] == now["status"]:
            continue
        qs = sorted(set(was["q"]) | set(now["q"]))
        moved = ", ".join(f"Q{q} {_pct(was['q'].get(q))}→{_pct(now['q'].get(q))}" for q in qs
                          if was["q"].get(q) != now["q"].get(q))
        line = f"  {who}: {a:g} → {b:g}" + (f"  ({moved})" if moved else "") + \
            (f"  [{was['status']} → {now['status']}]" if was["status"] != now["status"] else "")
        (down if b < a or (was["status"] == "GRADED" and now["status"] != "GRADED") else up).append(line)
    print(f"Graded {len(ids)} submission(s) again without saving.")
    print(f"{len(up)} went up, {len(down)} went down, {len(ids) - len(up) - len(down)} unchanged.")
    if down:
        print("\nWent down (check these before re-grading for real):", *down, sep="\n")
    if up:
        print("\nWent up:", *up, sep="\n")
    return 1 if down else 0


def _pct(x) -> str:
    return "—" if x is None else f"{x:.0%}"


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="python -m autograder.regress", description=__doc__.split("\n\n")[0])
    p.add_argument("action", choices=["save", "check"])
    p.add_argument("--assignment", type=int, help="only this assignment's submissions")
    p.add_argument("--workers", type=int, default=settings.grading_workers)
    a = p.parse_args(argv)
    init_engine(settings.database_url)
    return save(a.assignment) if a.action == "save" else check(a.assignment, a.workers)


if __name__ == "__main__":
    sys.exit(main())
