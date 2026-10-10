import csv
import json

from pdfgen import make_pdf
from samples import C_SUM, JAVA_REV, PY_FACT
from test_similarity import BUBBLE, BUBBLE_DISGUISED, BUBBLE_OWN

from docextract.cli import main


def test_extract_prints_and_writes(tmp, capsys):
    pdf = make_pdf(tmp / "s.pdf", [("h", "Q1"), ("code", PY_FACT, "mono_offset"),
                                   ("h", "Q2"), ("code", JAVA_REV, "mono_offset")])
    assert main(["extract", pdf, "--out", str(tmp / "out")]) == 0
    out = capsys.readouterr().out
    assert "Question 1 (python)" in out and "Question 2 (java)" in out
    assert (tmp / "out" / "q1" / "main.py").read_text().startswith("def fact")
    assert (tmp / "out" / "q2" / "ReverseString.java").exists()
    assert json.loads((tmp / "out" / "extraction.json").read_text())["programs"]


def test_extract_json(tmp, capsys):
    pdf = make_pdf(tmp / "s.pdf", [("h", "Q1"), ("code", C_SUM, "mono_offset")])
    main(["extract", pdf, "--json"])
    assert json.loads(capsys.readouterr().out)["programs"][0]["language"] == "c"


def test_batch_over_classroom_folder(tmp, capsys):
    folder = tmp / "Assignment 3"
    folder.mkdir()
    for name, code in [("Alice Roy", BUBBLE), ("Bob Paul", BUBBLE_DISGUISED),
                       ("Carol Das", BUBBLE_OWN)]:
        make_pdf(folder / f"{name}.pdf", [("h", "Q1. Bubble sort"), ("code", code, "mono_offset"),
                                          ("p", "Output: 1 2 3")])
    (folder / "Dipak Sen.pdf").write_bytes(b"corrupted upload")
    make_pdf(folder / "Esha Ghosh.pdf", [("p", "Sorry sir, I will submit tomorrow.")])

    out = tmp / "results"
    assert main(["batch", str(folder), "--out", str(out)]) == 0
    rows = list(csv.DictReader(open(out / "extraction_report.csv")))
    status = {r["student"]: r["status"] for r in rows}
    assert status == {"Alice Roy": "OK", "Bob Paul": "OK", "Carol Das": "OK",
                      "Dipak Sen": "ERROR", "Esha Ghosh": "NO_CODE"}
    sim = list(csv.DictReader(open(out / "similarity.csv")))
    assert [(r["student_a"], r["student_b"]) for r in sim] == [("Alice Roy", "Bob Paul")]
    html = (out / "similarity.html").read_text()
    assert "Alice Roy" in html and 'class="hit"' in html
    assert (out / "students" / "Alice_Roy" / "q1" / "main.c").exists()
    assert (out / "students" / "Alice_Roy" / "q1" / "claimed_output.txt").read_text() == "1 2 3\n"


def test_batch_html_escapes_student_content(tmp):
    folder = tmp / "f"
    folder.mkdir()
    evil = 'printf("<script>alert(1)</script>");'
    for n in ("a", "b"):
        make_pdf(folder / f"{n}.pdf", [("h", "Q1"), ("code", C_SUM.replace('printf("Sum = %d\\n", a + b);', evil), "mono_offset")])
    main(["batch", str(folder), "--out", str(tmp / "o")])
    html = (tmp / "o" / "similarity.html").read_text()
    assert "<script>alert" not in html and "&lt;script&gt;" in html


def test_batch_empty_folder(tmp):
    (tmp / "empty").mkdir()
    assert main(["batch", str(tmp / "empty"), "--out", str(tmp / "o")]) == 1
