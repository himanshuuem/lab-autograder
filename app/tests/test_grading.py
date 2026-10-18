"""Grade the whole demo class: real PDF extraction, real compile+run, real similarity."""
import pytest
from conftest import HAVE_JAVAC, FakeClassroom, LocalSandbox, fresh_db_url
from sqlalchemy import select

from autograder import grading
from autograder.db import init_engine, session_scope
from autograder.models import Assignment, Job, SimilarityPair


@pytest.fixture(scope="module")
def graded(tmp_path_factory):
    from autograder import config
    d = tmp_path_factory.mktemp("g")
    config.settings.database_url = fresh_db_url(d)
    config.settings.data_dir = str(d / "data")
    FakeClassroom.provider = None
    init_engine(config.settings.database_url)
    cc, sb = FakeClassroom(), LocalSandbox()
    with session_scope() as db:
        grading.sync_courses(db, cc)
    with session_scope() as db:
        a = db.scalar(select(Assignment))
        a.time_limit_s = 1.0
        j = Job(kind="grade", assignment_id=a.id)
        db.add(j)
        db.flush()
        jid = j.id
    summary = grading.run_grade_job(jid, cc, sb)
    s = session_scope().__enter__()
    a = s.scalar(select(Assignment))
    by_name = {x.student.name: x for x in a.submissions}
    return summary, a, by_name, s


def codes(sub):
    return {(f["code"], f["q"]) for f in sub.flags}


def test_summary_and_tests_imported(graded):
    summary, a, *_ = graded
    assert summary["submissions"] == 11
    assert [(q.label, len(q.tests)) for q in a.questions] == [("1", 2), ("2", 1)]
    assert a.last_graded_at is not None


def test_correct_c_full_marks(graded):
    s = graded[2]["Ananya Bose"]
    assert s.status == "GRADED" and s.auto_score == 20
    assert all(p.claimed_status == "MATCHES_ACTUAL" for p in s.programs)


def test_disguised_copy_flagged_on_both_questions(graded):
    _, a, by, db = graded
    rohit = by["Rohit Mondal"]
    assert rohit.auto_score == 20       # copying never changes the score automatically
    assert {("SIMILAR_CODE", "1"), ("SIMILAR_CODE", "2")} <= codes(rohit)
    pairs = db.scalars(select(SimilarityPair)).all()
    names = {frozenset((p.sub_a.student.name, p.sub_b.student.name)) for p in pairs}
    assert names == {frozenset(("Ananya Bose", "Rohit Mondal"))}


def test_word_damaged_python_still_full_marks(graded):
    s = graded[2]["Sneha Paul"]
    assert s.auto_score == 20 and not s.needs_review
    assert s.programs[0].repairs.get("auto_capital_fixed") == 2
    assert s.extraction["repairs"]["smart_quote"] == 2


def test_fabricated_output_flagged(graded):
    s = graded[2]["Arjun Saha"]
    q1 = s.programs[0]
    assert q1.language == "cpp" and q1.tests_passed == 0 and q1.claimed_status == "MATCHES_EXPECTED_ONLY"
    assert ("POSSIBLE_FABRICATED_OUTPUT", "1") in codes(s)
    assert s.auto_score == 10 and s.needs_review


def test_compile_error(graded):
    s = graded[2]["Kunal Ghosh"]
    q1 = s.programs[0]
    assert q1.compile_status == "COMPILE_ERROR" and "error" in q1.compile_output
    assert [r.status for r in q1.runs] == ["NOT_RUN", "NOT_RUN"]
    assert ("COMPILE_ERROR", "1") in codes(s) and s.auto_score == 10


def test_infinite_loop_and_late(graded):
    s = graded[2]["Mehul Das"]
    assert s.programs[1].runs[0].status == "TLE"
    assert ("LATE", None) in codes(s) and s.auto_score == 10


def test_feedback_for_the_demo_class(graded):
    from autograder.feedback import feedback_text
    by = graded[2]
    t = feedback_text(by["Kunal Ghosh"])
    assert "Score: 10 / 20" in t and "Question 1: the program does not compile." in t
    t = feedback_text(by["Mehul Das"])
    assert "Turned in late." in t and "took too long" in t
    t = feedback_text(by["Arjun Saha"])   # flagged for output the code can't print: not the student's to see
    assert "Question 1:" in t and "wrong output" in t and "fabricat" not in t.lower()
    assert "Rohit" not in feedback_text(by["Ananya Bose"])
    assert "No file was turned in" in feedback_text(by["Debjit Sen"])


def test_scanned_pdf_needs_review(graded):
    s = graded[2]["Ishita Roy"]
    assert ("OCR_USED", None) in codes(s) and s.needs_review
    assert not any(c == "POSSIBLE_FABRICATED_OUTPUT" for c, _ in codes(s))
    assert all(p.ocr for p in s.programs)


def test_word_submission_with_screenshot_outputs(graded):
    s = graded[2]["Riya Sen"]
    assert s.status == "GRADED" and s.auto_score == 20 and not s.needs_review
    assert s.files[0]["kind"] == "office"
    assert s.extraction["images_read"] == 2 and s.extraction["ocr_pages"] == []
    assert [p.language for p in s.programs] == ["c", "python"]
    assert all(p.claimed_from_image and p.claimed_status == "MATCHES_ACTUAL" for p in s.programs)


def test_faked_screenshot_output_flagged(graded):
    s = graded[2]["Aman Gupta"]
    assert [f["kind"] for f in s.files] == ["pdf", "image"]
    q1, q2 = s.programs
    assert q1.claimed_status == "MATCHES_ACTUAL" and q1.tests_passed == 2
    assert q2.tests_passed == 0 and q2.claimed_status == "MATCHES_EXPECTED_ONLY" and q2.claimed_from_image
    fab = [f for f in s.flags if f["code"] == "POSSIBLE_FABRICATED_OUTPUT"]
    assert fab and "screenshot" in fab[0]["msg"]
    assert s.auto_score == 10


def test_not_submitted(graded):
    s = graded[2]["Debjit Sen"]
    assert s.status == "NO_SUBMISSION" and s.auto_score == 0 and codes(s) == {("NOT_SUBMITTED", None)}


@pytest.mark.skipif(not HAVE_JAVAC, reason="javac not installed (the Java runner image has it)")
def test_java_full_marks(graded):
    s = graded[2]["Priya Dutta"]
    assert s.auto_score == 20 and s.programs[0].language == "java"


def test_java_class_name_detected(graded):
    s = graded[2]["Priya Dutta"]
    assert [p.language for p in s.programs] == ["java", "java"]


def test_regrade_one_keeps_override(graded):
    _, a, by, db = graded
    s = by["Kunal Ghosh"]
    s.override_score = 15
    db.commit()
    with session_scope() as d2:
        j = Job(kind="grade_one", assignment_id=a.id, submission_id=s.id)
        d2.add(j)
        d2.flush()
        jid = j.id
    grading.run_grade_job(jid, FakeClassroom(), LocalSandbox())
    db.expire_all()
    s = db.get(type(s), s.id)
    assert s.override_score == 15 and s.final_score == 15 and s.auto_score == 10


def test_cleared_pair_removes_flags(graded):
    _, a, by, db = graded
    for p in db.scalars(select(SimilarityPair)):
        p.verdict = "cleared"
    grading.run_similarity(db, a)
    db.commit()
    assert not any(c == "SIMILAR_CODE" for c, _ in codes(by["Rohit Mondal"]))
    assert {p.verdict for p in db.scalars(select(SimilarityPair))} == {"cleared"}


def test_question_mapping_fallbacks():
    from types import SimpleNamespace as N
    qs = [N(label="1"), N(label="2")]
    progs = [N(question="5"), N(question="6")]
    mapped, extra, notes = grading._map_programs(qs, progs)
    assert mapped == {"1": progs[0], "2": progs[1]} and notes
    only = N(question="3")
    mapped, extra, _ = grading._map_programs([N(label="1")], [only])
    assert mapped == {"1": only} and extra == []
    mapped, extra, _ = grading._map_programs(qs, [N(question="2"), N(question="9")])
    assert list(mapped) == ["2"] and [p.question for p in extra] == ["9"]


def test_unreadable_attachment(graded):
    """A student who attaches only something unreadable gets an error to review, not a crash.
    (Reuses the module's database: resetting it under an open transaction would block on PostgreSQL.)"""
    from autograder.models import Course, Submission

    class CC:
        def submissions(self, c, w):
            return [{"id": "x1", "student": {"id": "u1", "name": "Zed"}, "state": "TURNED_IN",
                     "files": [{"file_id": "z", "title": "project.zip"}]}]

        def download(self, fid):
            return "project.zip", b"PK\x03\x04junk"

    with session_scope() as db:
        c = Course(ext_id="unreadable-test", name="C")
        db.add(c)
        db.flush()
        a = Assignment(course_id=c.id, ext_id="w", title="A")
        db.add(a)
        db.flush()
        aid = a.id
    (sid,) = grading.sync_submissions(aid, CC())
    with session_scope() as db:
        s = db.get(Submission, sid)
        assert s.pdf_path is None and "project.zip" in s.error
        grading.grade_submission(db, LocalSandbox(), s)
        assert s.status == "ERROR" and s.needs_review
        assert s.flags[0]["code"] == "UNREADABLE_FILE"


def test_download_failure_keeps_the_earlier_copy(graded):
    """A network blip during a re-grade grades the copy downloaded last time instead of
    turning the answer into a zero; a student who changed their files is not graded on
    the old ones."""
    from autograder.clients import ServiceError
    from autograder.models import Course, Submission

    class CC:
        fail, files = False, [{"file_id": "m1", "title": "Main.java"}, {"file_id": "m2", "title": "Car.java"}]

        def submissions(self, c, w):
            return [{"id": "y1", "student": {"id": "u-blip", "name": "Ira"}, "state": "TURNED_IN",
                     "files": [dict(f) for f in self.files]}]

        def download(self, fid):
            if self.fail and fid == "m2":
                raise ServiceError("Classroom: Unable to find the server at www.googleapis.com")
            return "x.java", b'public class Main { public static void main(String[] a) { System.out.println("hi"); } }'

    with session_scope() as db:
        c = Course(ext_id="blip-test", name="C")
        db.add(c)
        db.flush()
        a = Assignment(course_id=c.id, ext_id="w", title="A")
        db.add(a)
        db.flush()
        aid = a.id
    cc = CC()
    (sid,) = grading.sync_submissions(aid, cc)
    with session_scope() as db:
        first = db.get(Submission, sid).pdf_path
        assert first and not db.get(Submission, sid).error
    before = open(first, "rb").read()

    cc.fail = True
    grading.sync_submissions(aid, cc)
    with session_scope() as db:
        s = db.get(Submission, sid)
        assert s.pdf_path == first and not s.error
        assert open(first, "rb").read() == before            # not overwritten by a partial copy
        assert any("downloaded earlier" in f.get("note", "") for f in s.files)

    cc.files = cc.files + [{"file_id": "m3", "title": "New.java"}]
    grading.sync_submissions(aid, cc)
    with session_scope() as db:
        s = db.get(Submission, sid)
        notes = [f["note"] for f in s.files if "note" in f]
        assert notes == ["Car.java: download failed (Classroom: Unable to find the server at www.googleapis.com)"]


def test_unchanged_submissions_are_not_downloaded_again(graded):
    from autograder.models import Course, Submission

    class CC:
        updated, calls = "2026-09-01T10:00:00Z", 0

        def submissions(self, c, w):
            return [{"id": "z1", "student": {"id": "u-same", "name": "Noor"}, "state": "TURNED_IN",
                     "update_time": self.updated, "files": [{"file_id": "n1", "title": "Main.java"}]},
                    {"id": "z2", "student": {"id": "u-none", "name": "Omar"}, "state": "CREATED",
                     "update_time": self.updated, "files": []}]

        def download(self, fid):
            self.calls += 1
            return "Main.java", b'public class Main { public static void main(String[] a) { } }'

    with session_scope() as db:
        c = Course(ext_id="same-test", name="C")
        db.add(c)
        db.flush()
        a = Assignment(course_id=c.id, ext_id="w", title="A")
        db.add(a)
        db.flush()
        aid = a.id
    cc = CC()
    sid, _ = grading.sync_submissions(aid, cc)
    assert cc.calls == 1
    with session_scope() as db:
        first = db.get(Submission, sid).pdf_path
        assert db.get(Submission, sid).source_updated == cc.updated
    grading.sync_submissions(aid, cc)                              # nothing changed in Classroom
    assert cc.calls == 1
    with session_scope() as db:
        s = db.get(Submission, sid)
        assert s.pdf_path == first and not s.error and s.files[0]["kind"] == "text"
    grading.sync_submissions(aid, cc, fresh=True)                  # the teacher asked for everything
    assert cc.calls == 2
    cc.updated = "2026-09-02T08:00:00Z"                            # the student changed their work
    grading.sync_submissions(aid, cc)
    assert cc.calls == 3


def test_migration_adds_new_columns(tmp_path):
    from sqlalchemy import create_engine, inspect
    from autograder.db import Base, _add_missing_columns
    e = create_engine(f"sqlite:///{tmp_path}/old.db")
    Base.metadata.create_all(e)
    with e.begin() as c:
        c.exec_driver_sql("ALTER TABLE program_results DROP COLUMN claimed_from_image")
    assert _add_missing_columns(e) == ["program_results.claimed_from_image"]
    assert "claimed_from_image" in {c["name"] for c in inspect(e).get_columns("program_results")}
    assert _add_missing_columns(e) == []
