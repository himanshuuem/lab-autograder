import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "packages" / "docextract" / "tests"))
from pdfgen import make_pdf  # noqa: E402

from autograder.assignment_parser import parse_assignment_pdf
from classroom_mcp.demo_provider import DemoProvider


def test_demo_assignment(tmp_path):
    p = tmp_path / "a.pdf"
    p.write_bytes(DemoProvider().download_file("f-assignment3")["data"])
    qs = parse_assignment_pdf(str(p))
    assert [(q.label, q.title) for q in qs] == [("1", "Bubble sort"), ("2", "Sum of digits")]
    assert qs[0].tests == [("5\n4 1 3 9 2\n", "1 2 3 4 9"), ("3\n3 2 1\n", "1 2 3")]
    assert qs[1].tests == [("1234\n", "10")]
    assert "ascending" in qs[0].statement[0]


def test_inline_and_prose(tmp_path):
    pdf = make_pdf(tmp_path / "a.pdf", [
        ("h", "Q1. Add"),
        ("p", "Input a number pair and print the sum."),     # prose, not a label
        ("p", "Input: 3 4"), ("p", "Output: 7"),
        ("p", "Explanation: 3 plus 4 is 7."),
        ("h", "Q2. Hello"),
        ("p", "Print a greeting. There is no input."),
        ("p", "Sample Output:"), ("code", "Hello, IIEST!", "mono_spaces"),
        ("p", "Constraints: none"),
    ])
    qs = parse_assignment_pdf(pdf)
    assert qs[0].tests == [("3 4\n", "7")]
    assert "Input a number pair and print the sum." in qs[0].statement
    assert qs[1].tests == [("", "Hello, IIEST!")]


def test_output_block_ends_at_prose(tmp_path):
    pdf = make_pdf(tmp_path / "a.pdf", [
        ("h", "Question 1"), ("p", "Sample Input:"), ("code", "2\n5 6", "mono_spaces"),
        ("p", "Sample Output:"), ("code", "11", "mono_spaces"),
        ("p", "Your program must handle negative numbers too."),
    ])
    (q,) = parse_assignment_pdf(pdf)
    assert q.tests == [("2\n5 6\n", "11")]
    assert "negative" in q.statement[-1]


def test_no_questions(tmp_path):
    pdf = make_pdf(tmp_path / "a.pdf", [("p", "Read chapter 4.")])
    assert parse_assignment_pdf(pdf) == []


def test_plain_numbered_questions(tmp_path):
    """Real sheet: an "Assignment 1" title, then questions numbered "1." "2." with no Q,
    and numbered sub-lists inside a question that must not start new questions."""
    pdf = make_pdf(tmp_path / "a.pdf", [
        ("p", "Object Oriented Programming Lab."), ("h", "Assignment 1"),
        ("p", "1. Create a class Car with the following data members:"), ("p", "  - Brand"),
        ("p", "2. Design a class Student to store the student's name and CGPA."),
        ("p", "3. Create a class Circle with a data member radius."),
        ("p", "Write methods to:"), ("p", "    1. Increase speed"), ("p", "    2. Decrease speed"),
        ("p", "4. Car Speed Control"),
        ("p", "Sample Input:"), ("code", "50", "mono_spaces"), ("p", "Sample Output:"), ("code", "Speed: 50", "mono_spaces"),
    ])
    qs = parse_assignment_pdf(pdf)
    assert [q.label for q in qs] == ["1", "2", "3", "4"]
    assert qs[0].title.startswith("Create a class Car") and qs[3].title == "Car Speed Control"
    assert qs[3].tests == [("50\n", "Speed: 50")]
    assert any("Increase speed" in s for s in qs[2].statement)
