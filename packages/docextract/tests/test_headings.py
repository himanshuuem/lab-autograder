"""Heading styles found in real submissions, and documents with no headings at all."""
from pdfgen import make_pdf

from docextract import extract_submission

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
CIRCLE = """public class Circle {
    public static void main(String[] args) {
        double r = 2;
        System.out.println("Area : " + 3.14 * r * r);
    }
}"""
ATM = """import java.util.Scanner;
public class ATM {
    public static void main(String[] args) {
        int pin = 1234;
        System.out.println("1. Deposit");
        System.out.println("2. Withdraw");
    }
}"""


def labels(tmp, blocks):
    r = extract_submission(make_pdf(tmp / "s.pdf", blocks))
    return r, [p.question for p in r.programs]


def test_question_text_copied_with_plain_numbers(tmp):
    r, labs = labels(tmp, [
        ("p", "Assignment 1"), ("p", "1. Create a class Car with the following data members:"),
        ("code", CAR, "mono_offset"), ("p", "Output:"), ("p", "Brand: Tata"),
        ("p", "2. Create a class Circle with a data member radius."), ("code", CIRCLE, "mono_offset"),
        ("p", "3. Design an ATM class with:"), ("code", ATM, "mono_offset"),
        ("p", "Output:"), ("p", "1. Deposit"), ("p", "2. Withdraw"),
    ])
    assert labs == ["1", "2", "3"]
    assert r.program("1").claimed_output == "Brand: Tata"
    assert r.program("3").claimed_output == "1. Deposit\n2. Withdraw"


def test_number_and_code_on_the_same_line(tmp):
    r, labs = labels(tmp, [("code", "1)  " + CAR, "mono_offset"), ("p", "Output: Brand: Tata"),
                           ("code", "2)  " + CIRCLE, "mono_offset")])
    assert labs == ["1", "2"]
    assert r.program("1").code.startswith("class Car {") and r.program("1").entrypoint == "CarDemo"


def test_q_heading_glued_to_code(tmp):
    r, labs = labels(tmp, [("code", "Q1- " + CAR, "mono_offset"), ("code", "Q2-" + CIRCLE, "mono_offset")])
    assert labs == ["1", "2"] and r.program("2").entrypoint == "Circle"


def test_underscore_and_quest_headings(tmp):
    _, labs = labels(tmp, [("p", "Ques_1"), ("code", CAR, "mono_offset"),
                           ("p", "Quest_2"), ("code", CIRCLE, "mono_offset")])
    assert labs == ["1", "2"]


def test_number_with_colon_alone_on_a_line(tmp):
    _, labs = labels(tmp, [("p", "Assignment - 1 :"), ("p", "1:"), ("code", CAR, "mono_offset"),
                           ("p", "2:"), ("code", CIRCLE, "mono_offset")])
    assert labs == ["1", "2"]


def test_code_line_numbers_are_not_headings(tmp):
    numbered = "\n".join(f"{i}. {ln}" for i, ln in enumerate(CIRCLE.splitlines(), 1))
    r, labs = labels(tmp, [("p", "Question 1"), ("code", numbered, "mono_offset")])
    assert labs == ["1"] and r.programs[0].entrypoint == "Circle"


def test_document_with_no_headings_is_split_by_program(tmp):
    """Real case: six complete programs one after another, each with an OUTPUT block,
    and no question headings anywhere."""
    r, labs = labels(tmp, [
        ("p", "ASSIGNMENT-1"), ("code", CAR, "mono_offset"), ("p", "OUTPUT:"), ("p", "Brand: Tata"),
        ("code", CIRCLE, "mono_offset"), ("p", "OUTPUT:"), ("p", "Area : 12.56"),
        ("code", ATM, "mono_offset"),
    ])
    assert labs == ["1", "2", "3"]
    assert [p.entrypoint for p in r.programs] == ["CarDemo", "Circle", "ATM"]
    assert r.program("1").claimed_output == "Brand: Tata" and r.program("2").claimed_output == "Area : 12.56"
    assert all(p.label_guessed for p in r.programs)
    assert r.program("3").code.startswith("import java.util.Scanner;")


def test_one_program_stays_one(tmp):
    r, labs = labels(tmp, [("p", "ASSIGNMENT-1"), ("code", CAR, "mono_offset"), ("p", "OUTPUT:"), ("p", "Brand: Tata")])
    assert labs == ["1"] and not r.programs[0].label_guessed


def test_same_answers_as_a_headed_doc_and_an_unheaded_pdf(tmp):
    """Real case: the Word file (with question headings) and a PDF of the same answers
    without headings. Each answer is counted once, under the heading's number."""
    from docextract import bundle
    headed = make_pdf(tmp / "a.pdf", [("p", "1. Create a class Car"), ("code", CAR, "mono_offset"),
                                      ("p", "2. Create a class Circle"), ("code", CIRCLE, "mono_offset"),
                                      ("p", "3. Design an ATM class"), ("code", ATM, "mono_offset")])
    plain = make_pdf(tmp / "b.pdf", [("p", "ASSIGNMENT-1"), ("code", CIRCLE, "mono_offset"),
                                     ("code", CAR, "mono_offset"), ("code", ATM, "mono_offset")])
    b = bundle([("Assignment.docx.pdf", open(headed, "rb").read()), ("Assignment.pdf", open(plain, "rb").read())])
    (tmp / "m.pdf").write_bytes(b.pdf)
    r = extract_submission(str(tmp / "m.pdf"))
    assert [(p.question, p.entrypoint) for p in r.programs] == [("1", "CarDemo"), ("2", "Circle"), ("3", "ATM")]


def test_all_questions_listed_first_then_all_answers(tmp):
    """Real case: the six questions copied at the top, then all six programs below."""
    r, labs = labels(tmp, [
        ("p", "1. Create a class Car with the following data members:"), ("p", "Brand, Model"), ("p", "Colour"),
        ("p", "2. Create a class Circle with a data member radius."), ("p", "Area"), ("p", "Circumference"),
        ("p", "3. Design an ATM class with:"), ("p", "pin"), ("p", "balance"),
        ("code", CAR, "mono_offset"), ("p", "Output:"), ("p", "Brand: Tata"),
        ("code", CIRCLE, "mono_offset"), ("code", ATM, "mono_offset"),
    ])
    assert len(labs) == 3 and [p.entrypoint for p in r.programs] == ["CarDemo", "Circle", "ATM"]
    assert all(p.label_guessed for p in r.programs)


def test_word_file_and_its_pdf_printout_count_once(tmp):
    from docextract import bundle
    doc = [("p", "1. Create a class Car"), ("code", CAR, "mono_offset"),
           ("p", "2. Create a class Circle"), ("code", CIRCLE, "mono_offset")]
    a, b = make_pdf(tmp / "a.pdf", doc), make_pdf(tmp / "b.pdf", doc)
    bb = bundle([("Assignment.docx.pdf", open(a, "rb").read()), ("Assignment.pdf", open(b, "rb").read())])
    (tmp / "m.pdf").write_bytes(bb.pdf)
    r = extract_submission(str(tmp / "m.pdf"))
    assert [(p.question, p.entrypoint) for p in r.programs] == [("1", "CarDemo"), ("2", "Circle")]


def test_question_headings_written_as_comments(tmp):
    r, labs = labels(tmp, [("code", "// Question 1 --\n" + CAR, "mono_offset"),
                           ("code", "/* Q2 */\n" + CIRCLE, "mono_offset"),
                           ("code", "# Question 3\nprint(int(input()) * 2)\nprint('done')", "mono_offset")])
    assert labs == ["1", "2", "3"]
    assert r.program("1").code.startswith("class Car {") and r.program("3").language == "python"


# ---------------------------------------------------------------- lines broken by the page width
WRAPPED = """public class Main {
    public static void main(String[] args) {
        String b = "Tata", m = "Nexon";
        System.out.println("Brand: " + b + " Model: " + m + "
Maxspeed: " + 160);
        System.out.println("Area of circle 1: " + 3 + " Area of circle 2:
" + 5);
    }
}"""


def test_string_broken_by_line_wrap_is_rejoined(tmp):
    r, _ = labels(tmp, [("p", "Question 1"), ("code", WRAPPED, "mono_offset")])
    code = r.programs[0].code
    assert '" Model: " + m + " Maxspeed: " + 160);' in code
    assert 'Area of circle 2: " + 5);' in code
    assert any("rejoined" in w or "wrapped" in w for w in r.programs[0].warnings) or r.programs[0].repairs


def test_python_strings_are_not_rejoined(tmp):
    py = 'name = "it\'s fine"\nprint("a")\nprint("b")'
    r, _ = labels(tmp, [("p", "Question 1"), ("code", py, "mono_offset")])
    assert r.programs[0].code.splitlines()[:3] == ['name = "it\'s fine"', 'print("a")', 'print("b")']


def test_answer_label_starts_the_code(tmp):
    r, labs = labels(tmp, [
        ("p", "1. Design a class Student and print the one with the highest CGPA."),
        ("p", "Hints: Array of objects"), ("code", "Student students[] = new Student[100];", "mono_offset"),
        ("p", "ANSWER:"), ("code", CIRCLE, "mono_offset"),
        ("p", "2. Next question"), ("code", CAR, "mono_offset"),
    ])
    assert labs == ["1", "2"] and r.program("1").code.startswith("public class Circle {")


def test_part_labels_inside_code_are_not_code(tmp):
    r, _ = labels(tmp, [("p", "Question 1"), ("code", CAR, "mono_offset"), ("p", "Part_2 :"),
                        ("code", CIRCLE.replace("class Circle", "class Two"), "mono_offset")])
    assert "Part_2" not in r.programs[0].code


def test_heading_in_a_code_font_is_not_code(tmp):
    r, labs = labels(tmp, [("code", "Q.1)\n" + CAR, "mono_offset"), ("code", "Q.2)\n" + CIRCLE, "mono_offset")])
    assert labs == ["1", "2"] and r.program("1").code.startswith("class Car {")


def test_part_label_in_a_code_font_is_not_code(tmp):
    r, _ = labels(tmp, [("p", "Question 1"), ("code", CAR + "\nPart_2 :\n" + CIRCLE.replace("class Circle", "class Two"),
                                                 "mono_offset")])
    assert "Part_2" not in r.programs[0].code


def test_imports_in_the_middle_move_to_the_top(tmp):
    two = CAR + "\nimport java.util.Scanner;\nclass Reader {\n    Scanner s;\n}"
    r, _ = labels(tmp, [("p", "Question 1"), ("code", "import java.util.*;\n" + two, "mono_offset")])
    lines = r.programs[0].code.splitlines()
    assert lines[:2] == ["import java.util.*;", "import java.util.Scanner;"]
    assert lines.count("import java.util.Scanner;") == 1


def test_op_and_screenshot_labels_start_the_output(tmp):
    for label in ("O/P:", "OP:", "O/P", "Screenshot:"):
        r, _ = labels(tmp, [("p", "Question 1"), ("code", CAR, "mono_offset"), ("p", label), ("p", "Brand: Tata")])
        assert r.programs[0].claimed_output == "Brand: Tata", label
        assert "Brand: Tata" not in r.programs[0].code


def test_java_lines_outside_every_class_are_dropped(tmp):
    stray = "Student students[] = new Student[100];\nradius;\n" + CAR + "\nO/P;\nBrand: Tata"
    r, _ = labels(tmp, [("p", "Question 1"), ("code", stray, "mono_offset")])
    code = r.programs[0].code
    assert code.startswith("class Car {") and code.rstrip().endswith("}")
    assert "students[]" not in code and r.programs[0].repairs.get("outside_class_removed")


ALLMAN = """import java.util.*;
class Car
{
    String brand;
}
public class CarDemo
    extends Object
{
    public static void main(String[] args)
    {
        Car c = new Car();
        System.out.println("ok");
    }
}"""


def test_braces_on_their_own_line_are_kept():
    from collections import Counter
    from docextract.cleanup import drop_java_outside_classes
    rep = Counter()
    assert drop_java_outside_classes(ALLMAN + "\n", rep).rstrip() == ALLMAN and not rep
    rep = Counter()
    out = drop_java_outside_classes("Student s[] = new Student[100];\n" + ALLMAN + "\nO/P;\nok\n", rep)
    assert out.rstrip() == ALLMAN and rep["outside_class_removed"] == 3
