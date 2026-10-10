"""The grading agent: Classroom -> PDF -> code -> sandbox -> scores, flags, similarity."""
from __future__ import annotations

import logging
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from docextract import Doc, bundle, compare_submissions, extract_submission
from sqlalchemy import select

from .assignment_parser import parse_assignment_pdf
from .clients import ClassroomClient, SandboxClient, ServiceError
from .config import settings
from .db import session_scope
from .evaluate import claimed_status, outputs_match
from .models import (Assignment, Course, Job, ProgramResult, Question, Run, SimilarityPair,
                     Student, Submission, TestCase)

log = logging.getLogger("grading")


def _now():
    return datetime.now(timezone.utc)


def _safe(s: str) -> str:
    return re.sub(r"[^\w.-]+", "_", s)[:120] or "x"


def flag(code: str, q: str | None = None, msg: str = "") -> dict:
    return {"code": code, "q": q, "msg": msg}


# ------------------------------------------------------------------ sync
def sync_courses(db, cc: ClassroomClient) -> int:
    n = 0
    for c in cc.courses():
        course = db.scalar(select(Course).where(Course.ext_id == c["id"]))
        if not course:
            course = Course(ext_id=c["id"], name=c["name"])
            db.add(course)
        course.name, course.section, course.link = c["name"], c.get("section") or "", c.get("link") or ""
        db.flush()
        for w in cc.coursework(c["id"]):
            a = db.scalar(select(Assignment).where(Assignment.course_id == course.id,
                                                   Assignment.ext_id == w["id"]))
            if not a:
                a = Assignment(course_id=course.id, ext_id=w["id"], title=w["title"],
                               max_points=w.get("max_points") or 100)
                db.add(a)
            a.title, a.description = w["title"], w.get("description") or ""
            a.due, a.materials, a.link = w.get("due"), w.get("materials") or [], w.get("link") or ""
            if w.get("max_points"):
                a.max_points = w["max_points"]
        n += 1
    return n


def import_tests(db, cc: ClassroomClient, a: Assignment) -> dict:
    """Parse the assignment's PDF material into questions + sample tests.
    Replaces tests that came from the PDF; keeps tests the TA added."""
    pdfs = [m for m in a.materials if m.get("title", "").lower().endswith(".pdf")] or a.materials
    if not pdfs:
        return {"questions": 0, "tests": 0, "message": "This assignment has no attached file to read tests from."}
    title, data = cc.download(pdfs[0]["file_id"])
    title = pdfs[0].get("title") or title
    b = bundle([(title, data)])        # the lab sheet may be a Word file too
    if not b.pdf:
        return {"questions": 0, "tests": 0, "message": "; ".join(b.errors) or f"{title} can't be read."}
    data = b.pdf
    d = os.path.join(settings.data_dir, "materials")
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, f"{a.id}.pdf")
    with open(path, "wb") as f:
        f.write(data)
    parsed = parse_assignment_pdf(path)
    existing = {q.label: q for q in a.questions}
    nt = 0
    for pos, pq in enumerate(parsed):
        q = existing.get(pq.label)
        if not q:
            q = Question(label=pq.label, position=pos)
            a.questions.append(q)
        q.title, q.statement = pq.title[:300], "\n".join(pq.statement)
        q.tests[:] = [t for t in q.tests if t.source != "pdf"]
        for i, (stdin, exp) in enumerate(pq.tests):
            q.tests.append(TestCase(stdin=stdin, expected=exp, source="pdf", position=i))
            nt += 1
    a.tests_imported = True
    return {"questions": len(parsed), "tests": nt,
            "message": f"Found {len(parsed)} question(s) and {nt} sample test(s) in {title}."}


def _pick_pdf(files: list[dict]) -> dict | None:
    if not files:
        return None
    pdfs = [f for f in files if f.get("title", "").lower().endswith(".pdf")]
    return (pdfs or files)[0]


MAX_ATTACHMENTS = 30   # some students attach one file per question, 12+ files


def sync_submissions(assignment_id: int, cc: ClassroomClient, progress=None) -> list[int]:
    """Fetch every submission and its PDF. Each student is saved as soon as
    their file is downloaded, so progress is visible and partial work survives."""
    with session_scope() as db:
        a = db.get(Assignment, assignment_id)
        course_ext, assign_ext = a.course.ext_id, a.ext_id
    folder = os.path.join(settings.data_dir, "submissions", str(assignment_id))
    os.makedirs(folder, exist_ok=True)
    subs = cc.submissions(course_ext, assign_ext)
    log.info("assignment %s: %d submission(s) listed in Classroom", assignment_id, len(subs))
    ids = []
    for n, s in enumerate(subs, 1):
        st = s["student"]
        if progress:
            progress(n - 1, len(subs), st["name"])
        files = (s.get("files") or [])[:MAX_ATTACHMENTS]
        pdf_path, pdf_file_id, error = None, None, ""
        got, notes = [], []
        for f in files:
            try:
                t0 = time.monotonic()
                title, data = cc.download(f["file_id"])
                got.append((f.get("title") or title or "attachment", data))
                log.info("  %d/%d %s: %s (%d KB, %.1fs)", n, len(subs), st["name"], f.get("title"),
                         len(data) // 1024, time.monotonic() - t0)
            except ServiceError as e:
                notes.append(f"{f.get('title')}: download failed ({e})")
                log.warning("  %d/%d %s: %s download failed: %s", n, len(subs), st["name"], f.get("title"), e)
        if got:
            b = bundle(got)
            notes += b.errors
            if b.pdf:
                pdf_path = os.path.join(folder, f"{_safe(s['id'])}.pdf")
                with open(pdf_path, "wb") as out:
                    out.write(b.pdf)
                pdf_file_id = files[0]["file_id"]
            kinds = {p["name"]: p["kind"] for p in b.parts}
            for f in files:
                t = f.get("title") or ""
                f["kind"] = kinds.get(t) or ("zip" if any(n.startswith(t + "/") for n in kinds) else None)
        if not pdf_path and files:
            error = "; ".join(notes) or "no readable file"
        file_notes = notes
        with session_scope() as db:
            stu = db.scalar(select(Student).where(Student.ext_id == st["id"]))
            if not stu:
                stu = Student(ext_id=st["id"], name=st["name"], email=st.get("email", ""))
                db.add(stu)
                db.flush()
            stu.name, stu.email = st["name"], st.get("email") or stu.email
            sub = db.scalar(select(Submission).where(Submission.assignment_id == assignment_id,
                                                     Submission.student_id == stu.id))
            if not sub:
                sub = Submission(assignment_id=assignment_id, student_id=stu.id, ext_id=s["id"])
                db.add(sub)
            sub.ext_id, sub.state, sub.late = s["id"], s.get("state", ""), bool(s.get("late"))
            sub.files = [*(s.get("files") or [])]
            if file_notes:
                sub.files = sub.files + [{"note": x} for x in file_notes]
            sub.pdf_path, sub.pdf_file_id, sub.error = pdf_path, pdf_file_id, error
            db.flush()
            ids.append(sub.id)
    if progress:
        progress(len(subs), len(subs), "")
    return ids


# ------------------------------------------------------------------ grade one
_TOPIC_STOP = {"class", "classes", "create", "design", "with", "the", "following", "data", "members", "member",
               "containing", "having", "and", "for", "store", "write", "methods", "method", "suitable", "java",
               "demo", "main", "public", "private", "static", "void", "string", "int", "double", "float", "new",
               "this", "return", "system", "out", "println", "print", "assignment", "program", "question",
               "objects", "object", "three", "two", "display", "details", "args", "using", "test"}


def _words(text: str) -> set[str]:
    """Words of names and titles, splitting CamelCase and snake_case: increaseSpeed -> increase, speed."""
    toks = re.findall(r"[A-Z]?[a-z]+|[A-Z]+(?![a-z])|\d+", text or "")
    return {t.lower() for t in toks if len(t) >= 3 and t.lower() not in _TOPIC_STOP}


def _place_by_topic(questions: list[Question], programs) -> None:
    """Programs numbered only by upload order (files named Car.java, Employee.java…) are
    placed under the question they are about: their class and file names against the
    question titles, helped by identifiers in the code against the question text."""
    guessed = [p for p in programs if getattr(p, "label_guessed", False)]
    if not guessed or not questions:
        return
    taken = {p.question for p in programs if not getattr(p, "label_guessed", False)}
    free = [q for q in questions if q.label not in taken]
    pairs = []
    for i, p in enumerate(guessed):
        stem = (getattr(p, "source_file", None) or "").rsplit("/", 1)[-1].rsplit(".", 1)[0]
        names = _words(" ".join(re.findall(r"\bclass\s+(\w+)", p.code or "")) + " " + stem)
        code = _words(" ".join(re.findall(r"[A-Za-z_]\w*", p.code or "")))
        for q in free:
            title, text = _words(q.title), _words(q.title) | _words(q.statement)
            score = 3 * len(names & title) + len(code & text)
            if names & title:
                pairs.append((score, i, q.label))
    placed: dict[int, str] = {}
    used = set()
    for score, i, label in sorted(pairs, key=lambda t: (-t[0], t[1])):
        if i in placed or label in used:
            continue
        placed[i] = label
        used.add(label)
    for i, p in enumerate(guessed):
        if i in placed:
            if placed[i] != p.question:
                p.warnings.append(f"placed under question {placed[i]} by its topic (the file name has no number)")
            p.question = placed[i]
        elif p.question in used or p.question in taken:
            p.question = f"{p.question}?"          # no question left for it: shown as an extra program


def _sheet_label(label: str, labels: list[str]) -> str | None:
    """The sheet's label for what the student wrote, when the two number differently:
    "5" or "Q5" for 4.5 (the part after the dot), "45" for 4.5 (the dot lost), "2.3" for 3,
    or "1" for the first question of a part (4.4 when the part is 4.4-4.7)."""
    base = (label or "").rstrip("?")
    if base in labels:
        return base
    if not re.fullmatch(r"\d{1,3}(?:\.\d{1,2})?", base):
        return None
    dotted = [l for l in labels if "." in l]
    if "." in base:
        minor = base.split(".")[1]
        return minor if minor in labels and not dotted else None
    by_minor = [l for l in dotted if l.split(".")[1] == base]
    if len(by_minor) == 1:
        return by_minor[0]
    squashed = [l for l in dotted if l.replace(".", "") == base]
    if len(squashed) == 1:
        return squashed[0]
    if dotted and 1 <= int(base) <= len(labels):
        return labels[int(base) - 1]
    return None


def _relabel(questions: list[Question], programs, guessed: bool) -> None:
    labels = [q.label for q in questions]
    taken = {p.question for p in programs if p.question in labels}
    for p in programs:
        if bool(getattr(p, "label_guessed", False)) != guessed or p.question in labels:
            continue
        to = _sheet_label(p.question, labels)
        if to and to not in taken:
            p.warnings.append(f"answer numbered {p.question} placed under question {to}")
            p.question = to
            taken.add(to)


def _map_programs(questions: list[Question], programs) -> tuple[dict, list, list[str]]:
    _relabel(questions, programs, guessed=False)
    _place_by_topic(questions, programs)
    _relabel(questions, programs, guessed=True)
    by_label = {p.question: p for p in programs}
    labels = [q.label for q in questions]
    notes = []
    if questions and not any(l in by_label for l in labels):
        if len(programs) == len(questions):
            notes.append("question numbers didn't match; programs matched to questions in order")
            return {q.label: p for q, p in zip(questions, programs)}, [], notes
        if len(questions) == 1 and programs:
            return {labels[0]: programs[0]}, programs[1:], notes
    mapped = {l: by_label[l] for l in labels if l in by_label}
    extra = [p for p in programs if p.question not in mapped]
    return mapped, extra, notes


def _first_error(compile_output: str) -> str | None:
    m = re.search(r"error: (.*)", compile_output or "")
    return m.group(1) if m else None


def _grade_by_checks(sb: SandboxClient, a: Assignment, q: Question, p, pr: ProgramResult,
                     tests: list, flags: list) -> None:
    """Score a question by requirement checks (checks.py): run the student's program once,
    and run the behaviour checks with AgCheck compiled next to their code."""
    from . import checks
    main = sb.run(p.language, p.code, [""], entrypoint=p.entrypoint or "Main", time_limit_s=a.time_limit_s)
    lines = checks.demo_error_lines(main.get("compile_output", "")) if main["compile_status"] == "COMPILE_ERROR" else None
    if lines:
        # the error the question asks students to show: grade the rest of the program
        fixed = checks.comment_out(p.code, lines)
        again = sb.run(p.language, fixed, [""], entrypoint=p.entrypoint or "Main", time_limit_s=a.time_limit_s)
        if again["compile_status"] != "COMPILE_ERROR":
            first = (_first_error(main.get("compile_output", "")) or "").strip()
            p.code, pr.code, main = fixed, fixed, again
            pr.warnings = list(pr.warnings or []) + [
                f"line {', '.join(map(str, sorted(lines)))} commented out before running: it has the compile error "
                f"the question asks for ({first[:120]})"]
    pr.compile_status, pr.compile_output = main["compile_status"], main.get("compile_output", "")[:20000]
    pr.tests_total, pr.tests_passed = len(tests), 0
    if main["compile_status"] in ("COMPILE_ERROR", "SANDBOX_ERROR"):
        why = "the code doesn't compile" if main["compile_status"] == "COMPILE_ERROR" else "sandbox error"
        for t in tests:
            pr.runs.append(Run(test_case_id=t.id, expected=t.expected, rule=t.rule, status="NOT_RUN",
                               passed=False, note=why))
        if main["compile_status"] == "COMPILE_ERROR":
            flags.append(flag("COMPILE_ERROR", q.label, (main.get("compile_output") or "")[:300]))
        pr.score = 0.0
        return
    out = main["tests"][0]
    # a program that reads its data from the keyboard: type some in, so the output checks
    # have something to look at
    shown, typed = out, False
    if out["status"] != "OK" and checks.needs_input(out["stderr"]):
        again = sb.run(p.language, p.code, [checks.KEYBOARD_INPUT], entrypoint=p.entrypoint or "Main",
                       time_limit_s=a.time_limit_s)
        if again.get("tests") and again["tests"][0]["stdout"].strip():
            shown, typed = again["tests"][0], True
    java_ids = [t.rule for t in tests if checks.is_harness_check(t.rule)]
    harness = {}
    if java_ids and p.language == "java":
        hr = sb.run("java", p.code + "\n" + checks.JAVA_HARNESS, checks.harness_tests(java_ids, p.code),
                    entrypoint=checks.CHECK_CLASS, time_limit_s=max(a.time_limit_s, 3.0))
        if hr["compile_status"] == "COMPILE_ERROR":
            msg = "the checks couldn't be compiled with this code: " + (hr.get("compile_output") or "")[:200]
            harness = {cid: (False, msg, "NOT_RUN") for cid in java_ids}
        else:
            for cid, tr in zip(java_ids, hr["tests"]):
                ok, msg = checks.parse_harness(tr["stdout"])
                if tr["status"] == "TLE":
                    ok, msg = False, "the student's method took too long (waiting for input or an endless loop?)"
                harness[cid] = (ok, msg, tr["status"])
    got, tw = 0.0, sum(t.weight for t in tests) or 1.0
    for t in tests:
        status = out["status"]
        if t.rule == "run":
            ok, note = checks.check_run(out["status"], out["stderr"])
        elif t.rule.startswith("out:lines:"):
            ok, note = checks.check_lines(shown["stdout"], int(t.rule.split(":")[2]))
        elif t.rule.startswith("out:"):
            ok, note = checks.check_output(t.rule[4:], shown["stdout"])
        elif t.rule.startswith("src:"):
            ok, note = checks.check_source(t.rule[4:], p.code)
        elif t.rule == "py:highest_cgpa":
            ok, note = checks.check_highest_cgpa(p.code, shown["stdout"], typed)
        elif t.rule == "py:discount15":
            ok, note = checks.check_discount(shown["stdout"])
        elif checks.is_harness_check(t.rule):
            ok, note, status = harness.get(t.rule, (False, "behaviour checks need Java code", "NOT_RUN"))
        else:
            ok, note = False, f"unknown check {t.rule}"
        if typed and t.rule.startswith(("out:", "py:")):
            note += f" (it reads the keyboard; grading typed {checks.KEYBOARD_NOTE})"
        pr.runs.append(Run(test_case_id=t.id, expected=t.expected, hidden=t.hidden, rule=t.rule,
                           status=status, stdin=checks.KEYBOARD_INPUT if typed and t.rule.startswith(("out:", "py:")) else t.stdin,
                           stdout=(shown if t.rule.startswith(("out:", "py:")) else out)["stdout"][:20000]
                           if not checks.is_harness_check(t.rule) else "",
                           stderr=out["stderr"][:5000] if t.rule == "run" else "", exit_code=out["exit_code"],
                           runtime_ms=out["runtime_ms"], passed=ok, note=note[:1000]))
        pr.tests_passed += ok
        got += t.weight if ok else 0
    pr.score = got / tw
    pr.claimed_status = claimed_status(p.claimed_output, [(out["stdout"], "")], fuzzy=p.claimed_from_image)
    if (pr.claimed_status == "NO_MATCH" and out["status"] == "OK" and not p.ocr
            and checks.shown_output_differs(p.claimed_output, out["stdout"], p.claimed_from_image)):
        flags.append(flag("POSSIBLE_FABRICATED_OUTPUT", q.label,
                          "The output the student showed is not what this code prints"
                          + (" (read from a screenshot: compare it by eye)" if p.claimed_from_image else "")))


_JAVA_WORDS = {"String", "System", "Math", "Scanner", "Object", "Integer", "Double", "Float", "Long", "Character",
               "Boolean", "List", "ArrayList", "Arrays", "Override", "Exception", "Main"}


def _borrow_classes(p, programs) -> None:
    """A class used here but written in another answer (Q4's Speed uses Q1's Car): copy it in,
    without its `public`, so the answer compiles on its own the way it did in the student's project."""
    if p.language != "java":
        return
    from docextract.cleanup import class_spans
    own = set(re.findall(r"\b(?:class|interface|enum)\s+(\w+)", p.code))
    used = set(re.findall(r"\bnew\s+([A-Z]\w*)\s*\(|\b(?:extends|implements)\s+([A-Z]\w*)|\b([A-Z]\w*)(?:\[\])?\s+[a-z_]\w*\s*[=;,)]",
                          p.code))
    need = {n for grp in used for n in grp if n} - own - _JAVA_WORDS
    added = []
    for other in programs:
        if other is p or other.language != "java" or not need:
            continue
        lines = other.code.split("\n")
        for name, a, b in class_spans(lines):
            if name in need:
                body = "\n".join(lines[a:b + 1])
                body = re.sub(r"^(\s*)public\s+(?=(?:abstract\s+|final\s+)*(?:class|interface|enum))", r"\1", body)
                p.code = p.code.rstrip("\n") + "\n\n" + body + "\n"
                need.discard(name)
                added.append(f"{name} (from question {other.question})")
    if added:
        p.warnings.append("used a class written in another answer, copied in: " + ", ".join(added))


def grade_submission(db, sb: SandboxClient, sub: Submission) -> None:
    a = sub.assignment
    sub.programs.clear()
    db.flush()
    flags: list[dict] = []
    sub.needs_review = False
    sub.graded_at = _now()
    if sub.late:
        flags.append(flag("LATE", msg="Turned in after the due date"))
    skipped = [f["note"] for f in (sub.files or []) if f.get("note")]
    if not sub.pdf_path:
        if sub.error:
            sub.status, sub.auto_score, sub.needs_review = "ERROR", None, True
            flags.append(flag("UNREADABLE_FILE", msg=sub.error))
        else:
            sub.status, sub.auto_score = "NO_SUBMISSION", 0.0
            flags.append(flag("NOT_SUBMITTED", msg="No file was turned in"))
        sub.flags = flags
        return
    try:
        res = extract_submission(sub.pdf_path)
    except Exception as e:
        sub.status, sub.error, sub.auto_score, sub.needs_review = "ERROR", f"could not read PDF: {e}", None, True
        sub.flags = flags + [flag("UNREADABLE_PDF", msg=str(e))]
        return
    sub.extraction = {"warnings": res.warnings, "repairs": res.repairs,
                      "ocr_pages": res.ocr_pages, "page_count": res.page_count,
                      "images_read": res.images_read}
    if skipped:
        flags.append(flag("FILE_SKIPPED", msg="; ".join(skipped)[:500]))
        sub.needs_review = True
    if res.ocr_pages:
        flags.append(flag("OCR_USED", msg=f"Scanned pages {res.ocr_pages} read by OCR; check the code"))
        sub.needs_review = True
    questions = list(a.questions)
    mapped, extra, notes = _map_programs(questions, res.programs)
    if notes:
        sub.extraction["warnings"] = sub.extraction["warnings"] + notes

    weighted, total_w, any_scored = 0.0, 0.0, False
    sandbox_failed = None
    for q in questions:
        p = mapped.get(q.label)
        total_w += q.weight
        if p is None:
            flags.append(flag("MISSING_QUESTION", q.label, "No code found for this question"))
            any_scored = True
            continue
        _borrow_classes(p, res.programs)
        pr = ProgramResult(question_label=q.label, language=p.language, code=p.code,
                           claimed_output=p.claimed_output, repairs=p.repairs, warnings=p.warnings,
                           ocr=p.ocr, claimed_from_image=p.claimed_from_image)
        sub.programs.append(pr)
        if p.needs_review:
            sub.needs_review = True
            if not p.ocr:
                flags.append(flag("EXTRACTION_REVIEW", q.label, "; ".join(p.warnings)[:300]))
        tests = list(q.tests)
        if not p.language:
            pr.compile_status, pr.score = "UNKNOWN_LANGUAGE", 0.0
            flags.append(flag("UNKNOWN_LANGUAGE", q.label, "Could not tell which language this is"))
            any_scored = True
            continue
        if not tests:
            pr.compile_status, pr.score = "NO_TESTS", None
            flags.append(flag("NO_TESTS", q.label, "Add test cases for this question"))
            continue
        if any(t.rule for t in tests):
            try:
                _grade_by_checks(sb, a, q, p, pr, tests, flags)
            except ServiceError as e:
                pr.compile_status, sandbox_failed = "SANDBOX_ERROR", str(e)
                continue
            if pr.compile_status == "SANDBOX_ERROR":
                sandbox_failed = pr.compile_output
                continue
            if any(not r.passed for r in pr.runs) and p.ocr:
                sub.needs_review = True
            weighted += q.weight * (pr.score or 0.0)
            any_scored = True
            continue
        try:
            r = sb.run(p.language, p.code, [t.stdin for t in tests],
                       entrypoint=p.entrypoint or "Main", time_limit_s=a.time_limit_s)
        except ServiceError as e:
            pr.compile_status, sandbox_failed = "SANDBOX_ERROR", str(e)
            continue
        pr.compile_status, pr.compile_output = r["compile_status"], r.get("compile_output", "")[:20000]
        pr.tests_total = len(tests)
        got = 0.0
        tw = sum(t.weight for t in tests) or 1.0
        pairs = []
        if r["compile_status"] in ("COMPILE_ERROR", "SANDBOX_ERROR"):
            for t in tests:
                pr.runs.append(Run(test_case_id=t.id, stdin=t.stdin, expected=t.expected, hidden=t.hidden,
                                   status="NOT_RUN", passed=False))
            if r["compile_status"] == "COMPILE_ERROR":
                flags.append(flag("COMPILE_ERROR", q.label, (r.get("compile_output") or "")[:300]))
            else:
                sandbox_failed = r.get("compile_output")
        else:
            for t, tr in zip(tests, r["tests"]):
                ok = tr["status"] == "OK" and outputs_match(tr["stdout"], t.expected, a.compare_mode)
                pr.runs.append(Run(test_case_id=t.id, stdin=t.stdin, expected=t.expected, hidden=t.hidden,
                                   status=tr["status"], stdout=tr["stdout"][:20000], stderr=tr["stderr"][:5000],
                                   exit_code=tr["exit_code"], runtime_ms=tr["runtime_ms"], passed=ok))
                pr.tests_passed += ok
                got += t.weight if ok else 0
                pairs.append((tr["stdout"], t.expected))
        pr.score = got / tw
        pr.claimed_status = claimed_status(p.claimed_output, pairs or [("", t.expected) for t in tests],
                                           fuzzy=p.claimed_from_image)
        # OCR'd code is unreliable, so a mismatch there says nothing about the student
        if pr.claimed_status == "MATCHES_EXPECTED_ONLY" and pr.tests_passed < pr.tests_total and not p.ocr:
            flags.append(flag("POSSIBLE_FABRICATED_OUTPUT", q.label,
                              "The submission shows the correct output, but this code does not produce it"
                              + (" (output read from a screenshot: compare it by eye)" if p.claimed_from_image else "")))
            sub.needs_review = True
        weighted += q.weight * pr.score
        any_scored = True

    for p in extra:
        sub.programs.append(ProgramResult(question_label=p.question, language=p.language, code=p.code,
                                          claimed_output=p.claimed_output, repairs=p.repairs,
                                          warnings=p.warnings + ["no matching question in the assignment"],
                                          compile_status="NOT_GRADED"))
    if not questions:
        flags.append(flag("NO_TESTS", None, "This assignment has no questions or test cases yet"))
        for p in res.programs:
            sub.programs.append(ProgramResult(question_label=p.question, language=p.language, code=p.code,
                                              claimed_output=p.claimed_output, repairs=p.repairs,
                                              warnings=p.warnings, compile_status="NO_TESTS"))
    if not res.programs:
        flags.append(flag("NO_CODE", None, "No code was found in the PDF"))
        sub.needs_review = True

    if sandbox_failed:
        sub.status, sub.error, sub.auto_score = "ERROR", f"sandbox: {sandbox_failed}"[:1000], None
        flags.append(flag("SANDBOX_ERROR", None, str(sandbox_failed)[:300]))
    else:
        sub.status, sub.error = "GRADED", ""
        sub.auto_score = round(a.max_points * weighted / total_w, 2) if any_scored and total_w else None
    sub.flags = flags


# ------------------------------------------------------------------ similarity
def run_similarity(db, a: Assignment) -> int:
    """Recompute similar pairs. Existing pairs are updated in place so their ids
    (and the TA's verdicts) survive re-grading."""
    existing = {(p.question_label, p.sub_a_id, p.sub_b_id): p
                for p in db.scalars(select(SimilarityPair).where(SimilarityPair.assignment_id == a.id))}
    subs = {s.id: s for s in a.submissions}
    for s in subs.values():
        s.flags = [f for f in (s.flags or []) if f["code"] != "SIMILAR_CODE"]
    by_q: dict[str, list[Doc]] = {}
    for s in subs.values():
        for p in s.programs:
            if p.code.strip() and p.language:
                by_q.setdefault(p.question_label, []).append(Doc(str(s.id), p.code, p.language))
    seen = set()
    for label, docs in by_q.items():
        for r in compare_submissions(docs, threshold=a.similarity_threshold,
                                     starter_code=a.starter_code or None):
            ia, ib = sorted((int(r.a), int(r.b)))
            la, lb = (r.lines_a, r.lines_b) if int(r.a) == ia else (r.lines_b, r.lines_a)
            key = (label, ia, ib)
            seen.add(key)
            pair = existing.get(key)
            if pair is None:
                pair = SimilarityPair(assignment_id=a.id, question_label=label, sub_a_id=ia, sub_b_id=ib)
                db.add(pair)
            pair.score, pair.jaccard, pair.low_confidence = r.score, r.jaccard, r.low_confidence
            pair.lines_a, pair.lines_b = [list(x) for x in la], [list(x) for x in lb]
            if pair.verdict == "cleared":
                continue
            for me, other in ((ia, ib), (ib, ia)):
                s = subs[me]
                s.flags = (s.flags or []) + [flag("SIMILAR_CODE", label,
                                                  f"{r.score:.0%} similar to {subs[other].student.name}")]
                s.needs_review = True
    for key, pair in existing.items():
        if key not in seen:
            db.delete(pair)
    return len(seen)


# ------------------------------------------------------------------ jobs
def _set_job(job_id: int, **kw):
    with session_scope() as db:
        j = db.get(Job, job_id)
        for k, v in kw.items():
            setattr(j, k, v)


def _grade_ids(sub_ids: list[int], job_id: int, sb: SandboxClient, done_start: int = 0):
    done = [done_start]

    def one(sid):
        try:
            with session_scope() as db:
                grade_submission(db, sb, db.get(Submission, sid))
        except Exception as e:  # never let one student break the batch
            log.exception("grading submission %s failed", sid)
            with session_scope() as db:
                s = db.get(Submission, sid)
                s.status, s.error, s.needs_review = "ERROR", f"{e.__class__.__name__}: {e}", True
        done[0] += 1
        _set_job(job_id, progress=done[0])

    with ThreadPoolExecutor(max_workers=max(1, settings.grading_workers)) as ex:
        list(ex.map(one, sub_ids))


def run_grade_job(job_id: int, cc: ClassroomClient | None = None, sb: SandboxClient | None = None):
    cc, sb = cc or ClassroomClient(), sb or SandboxClient()
    with session_scope() as db:
        job = db.get(Job, job_id)
        kind, aid, sid = job.kind, job.assignment_id, job.submission_id
        a = db.get(Assignment, aid)
        if kind == "grade" and not a.tests_imported and a.materials:
            _set_job(job_id, message="Reading test cases from the assignment PDF")
            import_tests(db, cc, a)
    if kind == "grade":
        _set_job(job_id, progress=0, total=0, message="Asking Google Classroom for the list of submissions")

        def fetched(done, total, name):
            _set_job(job_id, progress=done, total=total,
                     message=f"Downloading {done + 1} of {total}: {name}" if name else
                     f"Downloaded {total} submission(s)")
        ids = sync_submissions(aid, cc, fetched)
    else:
        ids = [sid]
    _set_job(job_id, progress=0, total=len(ids) + 1, message=f"Running {len(ids)} submission(s) in the sandbox")
    _grade_ids(ids, job_id, sb)
    with session_scope() as db:
        a = db.get(Assignment, db.get(Job, job_id).assignment_id)
        _set_job(job_id, message="Checking code similarity")
        pairs = run_similarity(db, a)
        a.last_graded_at = _now()
    return {"submissions": len(ids), "similar_pairs": pairs}
