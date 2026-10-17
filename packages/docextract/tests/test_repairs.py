"""What copying Java out of a PDF or a screenshot does to it, seen in real submissions, and
questions numbered 2.1, 4.5… the way the lab sheets number them."""
from collections import Counter

import pytest
from pdfgen import make_pdf

from docextract import cleanup, extract_submission
from docextract.segment import label_key

CAR = """class Car {
    String brand;
    Car(String b) { brand = b; }
}
public class CarDemo {
    public static void main(String[] args) {
        Car c = new Car("Tata");
        System.out.println("Brand: " + c.brand);
    }
}"""


def repair(code):
    rep = Counter()
    return cleanup.repair_java(code, rep), rep


VALID = '''import java.util.*;
/** A car.
 * With a doc comment */
class A {
    /*
     * block comment
     */
    int x = 5
        * 2;
    int[] a = {1,
       2};
    String s = "} string with a brace";
    char c = '}';

    T value;
}
public class Main { public static void main(String[] a) { System.out.println(new A().x); } }
'''


def test_code_that_compiles_is_never_changed():
    out, rep = repair(VALID)
    assert out == VALID and not rep


@pytest.mark.parametrize("broken,fixed,kind", [
    # the end of a /** comment from the previous page, and a "}" that closes nothing
    ("            *  Model\n            */\n}\nclass Car { }", "class Car { }", "stray_comment_removed"),
    ("Run | Debug\npublic class M { }", "public class M { }", "ide_text_removed"),
    ("class M {\n2025ITB085\n    int x;\n}", "class M {\n    int x;\n}", "header_text_removed"),
    ("class M {\n    int x;\n    6\n    int y;\n}", "class M {\n    int x;\n    int y;\n}", "line_number_removed"),
    ("class M {\n    9   public void f() { }\n}", "class M {\n    public void f() { }\n}", "line_number_removed"),
    ("1.   class Car {\n}", "class Car {\n}", "line_number_removed"),
    ("class M {\n    a       String model;\n}", "class M {\n    String model;\n}", "line_number_removed"),
    ('class M { void f() {\n    system.out.printin("x");\n} }', 'class M { void f() {\n    System.out.println("x");\n} }',
     "typo_fixed"),
    ('class M { void f() {\n    System.out..print1n("string s");\n} }',
     'class M { void f() {\n    System.out.println("string s");\n} }', "typo_fixed"),
    ("class M { void f(string s) { } }", "class M { void f(String s) { } }", "typo_fixed"),
    ('class M { M m = new M(name: "Anand", roll: 101); }', 'class M { M m = new M("Anand", 101); }', "ide_text_removed"),
    ("class M { int speed; void f(int a) {\nSpeed = speed + a;\n} }", "class M { int speed; void f(int a) {\nspeed = speed + a;\n} }",
     "auto_capital_fixed"),
    ("class S { int a; }\nclass S { int b; }", "class S { int b; }", "duplicate_class_removed"),
    ("class M {\n    void f() {\n        int x;\n", "class M {\n    void f() {\n        int x;\n}\n}", "closing_brace_added"),
])
def test_repairs(broken, fixed, kind):
    out, rep = repair(broken)
    assert out.strip() == fixed.strip() and rep[kind]


def test_keywords_glued_to_the_next_word():
    code = 'class Cow { }\nclass C { double r; double a() { returnMath.PI * r * r; } int b() { return2 * 3; }\n  Cow c = newCow(); }'
    out, rep = repair(code)
    assert "return Math.PI" in out and "return 2 * 3" in out and "new Cow()" in out and rep["space_restored"] == 3
    ok = "class C { int returnValue; Cow newCow() { return null; } int f() { return returnValue; } }"
    assert repair(ok)[0] == ok


def test_a_capitalised_class_is_not_lowercased():
    code = "class Speed { }\nclass M { void f() {\nSpeed s = new Speed();\n} }"
    assert repair(code)[0] == code


def test_label_order():
    assert sorted(["10", "4.10", "4.4", "2", "x"], key=label_key) == ["2", "4.4", "4.10", "10", "x"]


def test_answers_numbered_like_the_sheet(tmp):
    """Q4.4 / Assignment 4.5 / a bare 4.6 keep the whole number."""
    r = extract_submission(make_pdf(tmp / "s.pdf", [
        ("p", "Assignment- 4- 2nd Part"),
        ("p", "Q4.4"), ("code", CAR, "mono_offset"),
        ("p", "Assignment 4.5"), ("code", CAR.replace("CarDemo", "CarDemo2"), "mono_offset"),
        ("p", "Q 4.6)"), ("code", CAR.replace("CarDemo", "CarDemo3"), "mono_offset"),
    ]))
    assert [p.question for p in r.programs] == ["4.4", "4.5", "4.6"]


def test_bare_dotted_headings(tmp):
    r = extract_submission(make_pdf(tmp / "s.pdf", [
        ("p", "2.1 Create a class BankAccount"), ("code", CAR, "mono_offset"),
        ("p", "2.2 Create a class Student"), ("code", CAR.replace("CarDemo", "CarDemo2"), "mono_offset"),
    ]))
    assert [p.question for p in r.programs] == ["2.1", "2.2"]


def test_code_marker_on_the_same_line(tmp):
    """"Code :- class" then "Circle { double" (a justified paragraph): the class keeps its header."""
    r = extract_submission(make_pdf(tmp / "s.pdf", [
        ("p", "Q1"), ("p", "Code :- class"),
        ("code", 'Circle { double r = 2;\n  public static void main(String[] a) { System.out.println(r); }\n}', "mono_offset"),
    ]))
    assert r.programs[0].code.lstrip().startswith("class")


@pytest.mark.parametrize("broken,fixed,kind", [
    # the question text copied above the code: the end of a list typed as a comment
    ("import java.util.Scanner;\n                *  Deposit\n                *  Withdraw\nclass B { }",
     "import java.util.Scanner;\nclass B { }", "stray_comment_removed"),
    ("*/\nclass Display { }", "class Display { }", "stray_comment_removed"),
    # a /* whose closing line was question text, left out
    ("/*\n\npublic class BankAccount {\n    int x;\n}", "/*\n\n*/\npublic class BankAccount {\n    int x;\n}", "comment_closed"),
])
def test_comment_repairs(broken, fixed, kind):
    out, rep = repair(broken)
    assert out.strip() == fixed.strip() and rep[kind]


def test_a_commented_out_line_that_wrapped():
    code = ('class M { int salary; void f() {\n'
            '    // System.out.println("Trying the private salary: " +\n'
            'this.salary);\n'
            '    System.out.println(salary);\n} }')
    out, rep = repair(code)
    assert "\n// this.salary);\n" in out and "    System.out.println(salary);" in out and rep["wrapped_comment_joined"] == 1
    plain = "class M { void f() {\n    // see below\n    int x = 1;\n} }"
    assert repair(plain)[0] == plain


def test_a_sentence_comment_that_wrapped():
    # SK Assignment 3: compiler messages and notes typed as // comments, wrapped by the page width
    code = ('class M { int f(double t) {\n'
            '    //Prog.java:17: error: incompatible types: possible lossy conversion from double\n'
            'to int\n'
            '    //now changing both types to double in the Answer class method\n'
            'calculate the method works\n'
            '    return 1;\n} }')
    out, rep = repair(code)
    assert "// to int\n" in out and "// calculate the method works\n" in out and rep["wrapped_comment_joined"] == 2
    # code after a comment is untouched, even a statement split over lines
    for ok in ("class M { void f() {\n    // pick one\n    else x = 1;\n} }",
               "class M { void f() {\n    // the total\n    int total =\n        a + b;\n} }"):
        assert repair(ok)[0] == ok


def test_comment_opened_after_code_is_left_alone():
    code = "import java.util.*; /* the imports\n * we need */\nclass A { }\n"
    assert repair(code) == (code, Counter())


def test_a_class_named_like_a_c_keyword_keeps_its_capital():
    code = "class Auto extends Vehicle {\n    Auto(double d) { }\n}"
    assert cleanup.fix_autocapitalisation(code, "java", Counter()) == code


def test_a_class_named_like_a_keyword_keeps_its_capital_when_word_capitalised_class():
    # Word turned `class Auto` into `Class Auto` too (a real Assignment 5 submission)
    code = "Class Auto extends Vehicle {\n    Auto(double d) {\n        Super(d);\n    }\n}"
    fixed = cleanup.fix_autocapitalisation(code, "java", Counter())
    assert fixed == "class Auto extends Vehicle {\n    Auto(double d) {\n        super(d);\n    }\n}"


def test_word_capitalised_super_is_fixed_even_when_every_call_is_capitalised():
    code = "class Car extends Vehicle {\n    Car(double d) {\n        Super(d);\n    }\n}"
    fixed = cleanup.fix_autocapitalisation(code, "java", Counter())
    assert "        super(d);" in fixed
    named = "class Super { }\nclass B extends Super {\n    B() {\n        Super(1);\n    }\n}"   # their own class
    assert cleanup.fix_autocapitalisation(named, "java", Counter()) == named


def test_a_statement_split_over_short_lines(tmp):
    code = ('public class Bank {\n    public static void main(String[] args) {\n        Bank account1 =\n'
            '            new Bank(\n                "S101", "Rahul", 20000,\n                "Kolkata", 5, 5000);\n    }\n'
            '    Bank(String a, String b, int c, String d, int e, int f) { }\n}')
    r = extract_submission(make_pdf(tmp / "s.pdf", [("p", "Q1"), ("code", code, "prop_offset")]))
    assert '"S101", "Rahul", 20000,' in r.programs[0].code and "new Bank(" in r.programs[0].code
