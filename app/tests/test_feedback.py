"""Student feedback text: what is shown, and what must never be."""
from autograder.feedback import feedback_text
from autograder.models import Assignment, ProgramResult, Question, Run, Submission


def make(runs, *, compile_status="OK", status="GRADED", score=10.0, override=None, late=False, flags=()):
    a = Assignment(title="Assignment 3: Sorting", max_points=20.0)
    a.questions = [Question(label="1", weight=1.0), Question(label="2", weight=1.0)]
    p = ProgramResult(question_label="1", compile_status=compile_status, compile_output="main.c:3: error: expected ';'",
                      tests_passed=sum(r.passed for r in runs), tests_total=len(runs), runs=runs)
    return Submission(assignment=a, status=status, auto_score=score, override_score=override, late=late,
                      flags=list(flags), override_note="copied from Rohit?", programs=[p])


def run(passed, *, hidden=False, status="OK", stdin="5\n3 1 2", expected="1 2 3", stdout="3 2 1", **kw):
    return Run(passed=passed, hidden=hidden, status=status, stdin=stdin, expected=expected, stdout=stdout,
               stderr=kw.get("stderr", ""), rule=kw.get("rule", ""), note=kw.get("note", ""))


def test_sample_test_shows_input_expected_and_output():
    t = feedback_text(make([run(True), run(False)]))
    assert "Score: 10 / 20" in t
    assert "Question 1: 1 of 2 tests passed." in t
    assert "Test 2: wrong output." in t and "3 1 2" in t and "1 2 3" in t and "3 2 1" in t
    assert "Test 1" not in t   # passed tests are not listed


def test_hidden_test_shows_only_failed():
    t = feedback_text(make([run(False, hidden=True, stdin="SECRET-INPUT", expected="SECRET-OUT", stdout="x")]))
    assert "Test 1 (hidden): wrong output." in t
    assert "SECRET" not in t


def test_hidden_check_hides_what_it_found():
    t = feedback_text(make([run(False, hidden=True, rule="java:speed_max", expected="speed is capped",
                                note="speed reached 250")]))
    assert "Check 1: speed is capped: failed." in t and "250" not in t
    assert "0 of 1 check passed" in t


def test_review_flags_and_private_note_left_out():
    t = feedback_text(make([run(False)], flags=[{"code": "SIMILAR_CODE", "q": "1", "msg": "91% similar to Rohit"},
                                                {"code": "POSSIBLE_FABRICATED_OUTPUT", "q": "1", "msg": "x"}]))
    assert "Rohit" not in t and "SIMILAR" not in t and "FABRICATED" not in t and "copied" not in t


def test_compile_error_missing_question_late_and_override():
    t = feedback_text(make([run(False, status="NOT_RUN")], compile_status="COMPILE_ERROR", override=15.0, late=True))
    assert "Score: 15 / 20" in t and "Turned in late." in t
    assert "Question 1: the program does not compile." in t and "expected ';'" in t
    assert "Question 2: no code was found for this question." in t


def test_crash_shows_error_and_long_output_is_cut():
    t = feedback_text(make([run(False, status="RUNTIME_ERROR", stdout="\n".join(map(str, range(50))),
                                stderr="Segmentation fault")]))
    assert "crashed" in t and "Segmentation fault" in t
    assert "      ..." in t and "\n      49" not in t


def test_nothing_turned_in_and_ungradable():
    assert "No file was turned in" in feedback_text(make([], status="NO_SUBMISSION", score=0.0))
    t = feedback_text(make([], status="ERROR", score=None))
    assert "could not be graded automatically" in t and "Score" not in t
