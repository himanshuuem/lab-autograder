"""Feedback for the student, as plain text the TA pastes into Classroom's private comment.

Only what the student can act on: score, per-question test results, compiler errors,
and for sample tests the input, expected and actual output. Hidden tests show passed
or failed only, so their inputs can't be learned and hard-coded. Review flags
(similarity, output that the code can't print, OCR) and the TA's own note stay out.
"""
from __future__ import annotations

from .models import Submission

STATUS = {"OK": "wrong output", "TLE": "took too long (time limit)", "MLE": "used too much memory",
          "RUNTIME_ERROR": "crashed", "OUTPUT_LIMIT": "printed too much output",
          "NOT_RUN": "could not be run", "SANDBOX_ERROR": "could not be run"}
MAX_LINES, MAX_CHARS = 8, 600


def _num(x: float | None) -> str:
    return "-" if x is None else f"{x:g}"


def _block(text: str | None, indent: int = 6) -> list[str]:
    """Indented excerpt of program text, cut to a readable size."""
    pad = " " * indent
    text = (text or "").rstrip()
    if not text:
        return [f"{pad}(nothing)"]
    cut = text[:MAX_CHARS]
    lines = cut.splitlines()
    more = len(lines) > MAX_LINES or len(text) > MAX_CHARS
    lines = lines[:MAX_LINES]
    return [pad + l for l in lines] + ([f"{pad}..."] if more else [])


def _run_lines(i: int, r) -> list[str]:
    if r.passed:
        return []
    if r.rule:   # a requirement check (class structure, behaviour), see checks.py
        what = r.expected or "requirement check"
        if r.hidden:
            return [f"  Check {i}: {what}: failed."]
        out = [f"  Check {i}: {what}: failed."]
        if r.note:
            out += ["    Found:"] + _block(r.note)
        return out
    head = f"  Test {i}{' (hidden)' if r.hidden else ''}: {STATUS.get(r.status, r.status.lower())}."
    if r.hidden:
        return [head]
    out = [head, "    Input:"] + _block(r.stdin) + ["    Expected:"] + _block(r.expected)
    if r.status not in ("NOT_RUN", "SANDBOX_ERROR"):
        out += ["    Your program printed:"] + _block(r.stdout)
    if r.status == "RUNTIME_ERROR" and r.stderr:
        out += ["    Error:"] + _block(r.stderr)
    return out


def feedback_text(s: Submission) -> str:
    a = s.assignment
    lines = [a.title]
    if s.status == "NO_SUBMISSION":
        return "\n".join(lines + ["No file was turned in for this assignment."])
    if s.status == "ERROR" and s.override_score is None:
        return "\n".join(lines + ["Your submission could not be graded automatically. "
                                  "Your teacher will check it by hand."])
    if s.final_score is not None:
        lines.append(f"Score: {_num(s.final_score)} / {_num(a.max_points)}")
    if s.late:
        lines.append("Turned in late.")
    by_q = {p.question_label: p for p in s.programs}
    for q in a.questions:
        p = by_q.get(q.label)
        lines.append("")
        if p is None:
            lines.append(f"Question {q.label}: no code was found for this question.")
            continue
        if p.compile_status == "COMPILE_ERROR":
            lines += [f"Question {q.label}: the program does not compile.", "  Compiler output:"]
            lines += _block(p.compile_output, 4)
            continue
        if p.compile_status == "UNKNOWN_LANGUAGE":
            lines.append(f"Question {q.label}: the code could not be read as C, C++, Java or Python.")
            continue
        if not p.tests_total:
            lines.append(f"Question {q.label}: not tested.")
            continue
        word = "check" if all(r.rule for r in p.runs) else "test"
        lines.append(f"Question {q.label}: {p.tests_passed} of {p.tests_total} {word}"
                     f"{'' if p.tests_total == 1 else 's'} passed.")
        for i, r in enumerate(p.runs, 1):
            lines += _run_lines(i, r)
    if not a.questions and not s.programs:
        lines += ["", "No code was found in the submission."]
    return "\n".join(lines).strip() + "\n"
