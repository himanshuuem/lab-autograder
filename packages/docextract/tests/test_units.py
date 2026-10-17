from collections import Counter

import pytest

from docextract import cleanup, indent
from docextract.langdetect import detect_language, java_entrypoint
from docextract.pdfread import Line
from docextract.segment import code_score, segment
from samples import C_SUM, CPP_STACK, JAVA_REV, PY_CLASS, PY_FACT


def L(text, x=60.0, y=0.0, page=1, mono=True, cw=6.0, page_h=842.0):
    return Line(text=text, x=x, y=y, page=page, page_h=page_h, mono=mono, char_w=cw)


def lines_from(code, mono=True, start_y=100.0, cw=6.0):
    out, y = [], start_y
    for raw in code.split("\n"):
        if raw.strip():
            n = len(raw) - len(raw.lstrip())
            out.append(L(raw.strip(), x=60 + n * cw, y=y, mono=mono, cw=cw))
        y += 15
    return out


# ---------- cleanup ----------
@pytest.mark.parametrize("src,expected,kind", [
    ("print(\u201chi\u201d)", 'print("hi")', "smart_quote"),
    ("c = \u2018a\u2019", "c = 'a'", "smart_quote"),
    ("x = a \u2212 b", "x = a - b", "dash"),
    ("x = a \u2013 b", "x = a - b", "dash"),
    ("int\u00a0x;", "int x;", "special_space"),
    ("de\ufb01ne", "define", "ligature"),
    ("if (a \u2264 b)", "if (a <= b)", "symbol"),
    ("pr\u200bint(1)", "print(1)", "zero_width_char"),
])
def test_normalize_text(src, expected, kind):
    rep = Counter()
    assert cleanup.normalize_text(src, rep) == expected
    assert rep[kind] >= 1


def test_plain_ascii_is_untouched():
    rep = Counter()
    assert cleanup.normalize_text(C_SUM, rep) == C_SUM and not rep


def test_line_numbers_are_stripped_and_x_moved():
    ls = [L(f"{i} code{i}", x=60) for i in range(1, 6)]
    for ln in ls:
        ln.x_after_num = 90.0
    rep = Counter()
    out = cleanup.strip_line_numbers(ls, rep)
    assert [l.text for l in out] == [f"code{i}" for i in range(1, 6)]
    assert all(l.x == 90.0 for l in out) and rep["line_number_removed"] == 5


def test_data_lines_starting_with_numbers_are_kept():
    ls = [L("5 3"), L("10 2"), L("7 1"), L("2 9")]   # not increasing -> not line numbers
    assert [l.text for l in cleanup.strip_line_numbers(ls, Counter())] == ["5 3", "10 2", "7 1", "2 9"]


def test_header_footer_removed_but_repeated_code_kept():
    ls = []
    for p in (1, 2, 3):
        ls += [L("2023ITB045 Rahul", y=25, page=p), L("}", y=400, page=p),
               L(f"Page {p}", y=830, page=p)]
    rep = Counter()
    kept = cleanup.remove_headers_footers(ls, rep)
    assert [l.text for l in kept] == ["}", "}", "}"]
    assert rep["header_footer_removed"] == 6


@pytest.mark.parametrize("lang,src,expected", [
    ("python", "Def f(x):\n    Return x", "def f(x):\n    return x"),
    ("python", "Print('a')\nIf x:\n    pass", "print('a')\nif x:\n    pass"),
    ("python", "True\nNone\nFalse", "True\nNone\nFalse"),
    ("c", "Int main() {\n    Printf(\"x\");\n}", "int main() {\n    printf(\"x\");\n}"),
    ("cpp", "Cout << x;", "cout << x;"),
    ("java", "Public class A {}", "public class A {}"),
    ("java", "Class<?> c = A.class;", "Class<?> c = A.class;"),
    ("python", "Printer = 5", "Printer = 5"),
])
def test_fix_autocapitalisation(lang, src, expected):
    assert cleanup.fix_autocapitalisation(src, lang, Counter()) == expected


# ---------- language detection ----------
@pytest.mark.parametrize("code,lang", [
    (PY_FACT, "python"), (PY_CLASS, "python"), (C_SUM, "c"), (CPP_STACK, "cpp"),
    (JAVA_REV, "java"),
    ("#include <stdio.h>\n#include <iostream>\nusing namespace std;\nint main(){cout<<1;}", "cpp"),
    ("#include<bits/stdc++.h>\nint main(){}", "cpp"),
    ("hello world", None),
])
def test_detect_language(code, lang):
    assert detect_language(code)[0] == lang


@pytest.mark.parametrize("code,name", [
    (JAVA_REV, "ReverseString"),
    ("class Helper {}\nclass Main {\n public static void main(String[] a){}\n}", "Main"),
    ("public final class Q1 { }", "Q1"),
    ("int x;", None),
    # OCR read `class q4` as `class 94`: not a name Java can run, so it isn't chosen
    ("class 94 {\n public static void main(String[] a){}\n}", None),
])
def test_java_entrypoint(code, name):
    assert java_entrypoint(code) == name


# ---------- indentation ----------
def test_by_width_reproduces_monospace():
    assert indent.by_width(lines_from(PY_CLASS)) == PY_CLASS


def test_by_levels_handles_odd_widths():
    # proportional font: x offsets are not multiples of the char width
    ls = [L("def f():", x=60, y=0, mono=False), L("if x:", x=71.3, y=15, mono=False),
          L("return 1", x=82.9, y=30, mono=False), L("return 2", x=71.0, y=45, mono=False)]
    assert indent.by_levels(ls) == "def f():\n    if x:\n        return 1\n    return 2"


def test_blank_lines_restored_from_gaps():
    assert indent.by_width(lines_from("a = 1\n\nb = 2\nc = 3")) == "a = 1\n\nb = 2\nc = 3"


def test_python_compiles_never_executes(tmp_path):
    marker = tmp_path / "pwned"
    ok, err = indent.python_compiles(f"open({str(marker)!r}, 'w').write('x')")
    assert ok and err is None and not marker.exists()


def test_python_compiles_reports_error():
    ok, err = indent.python_compiles("def f(:\n  pass")
    assert not ok and "line 1" in err


# ---------- segmentation ----------
@pytest.mark.parametrize("text,is_code", [
    ("int main() {", True), ("}", True), ("for i in range(n):", True),
    ("x = x + 1", False),   # neutral alone; bridged when between code lines
    ("#include <stdio.h>", True), ("// swap the elements", True),
    ("Write a program to find the largest of three numbers.", False),
    ("The time complexity of this algorithm is O(n squared) in the worst case.", False),
    ("Name: Rahul Das", False),
])
def test_code_score_proportional(text, is_code):
    assert (code_score(L(text, mono=False)) >= 2) == is_code


@pytest.mark.parametrize("heading,label", [
    ("Q1.", "1"), ("Q 2:", "2"), ("Ques 3", "3"), ("Question No. 4 - Sorting", "4"),
    ("Experiment 5", "5"), ("Program-6", "6"), ("Assignment 7: Stacks", "7"), ("Prob #8", "8"),
])
def test_question_headings(heading, label):
    ls = [L(heading, mono=False, y=10)] + lines_from(C_SUM, start_y=30)
    secs = segment(ls)
    assert [s.label for s in secs] == [label]
    assert len(secs[0].code) == len(lines_from(C_SUM))


def test_code_comment_mentioning_question_is_not_a_heading():
    code = "// Question 2 is below\n" + C_SUM
    secs = segment(lines_from(code))
    assert len(secs) == 1 and len(secs[0].code) == len(lines_from(code))


def test_python_annotation_is_not_an_output_label():
    code = "output: int = 5\nprint(output)"
    secs = segment([L("Code:", mono=False, y=5)] + lines_from(code, start_y=20))
    assert not secs[0].had_output_marker
    assert [l.text for l in secs[0].code] == ["output: int = 5", "print(output)"]


def test_input_section_is_not_code():
    ls = ([L("Q1", mono=False, y=5), L("Input:", mono=False, y=20), L("5 3", mono=False, y=35)]
          + lines_from(C_SUM, start_y=60))
    sec = segment(ls)[0]
    assert "5 3" not in [l.text for l in sec.code]


def test_custom_question_regex():
    ls = [L("Part (a)", mono=False, y=5)] + lines_from(C_SUM, start_y=20)
    assert segment(ls, r"^Part \((\w)\)")[0].label == "a"


@pytest.mark.parametrize("code,name", [
    # main is not in the first public class
    ("public class Animal {}\npublic class Dog extends Animal {}\npublic class Main {\n"
     " public static void main(String[] a) {}\n}", "Main"),
    # a nested class declared before main
    ("public class Lab {\n static class Node { int v; }\n public static void main(String[] a) {}\n}", "Lab"),
    # braces and the word class inside strings/comments don't confuse it
    ('class A { String s = "{ class X {"; /* } class Y */ }\nclass B { public static void main(String[] a){} }', "B"),
    # no main at all: fall back to the public class
    ("class Helper {}\npublic class Shape {}", "Shape"),
])
def test_java_main_class_detection(code, name):
    assert java_entrypoint(code) == name
