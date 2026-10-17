"""Submissions made of several files: one file per question, helper classes,
output files, archives, notebooks, and files with odd or missing extensions."""
import io
import json
import shutil
import zipfile

import pytest
from conftest import needs_tesseract
from pdfgen import screenshot

from docextract import ConversionError, bundle, extract_submission, sniff, to_pdf
from docextract.convert import expand

needs_office = pytest.mark.skipif(shutil.which("soffice") is None, reason="LibreOffice not installed")


def extract(tmp, files):
    b = bundle(files)
    assert b.pdf, b.errors
    (tmp / "b.pdf").write_bytes(b.pdf)
    return b, extract_submission(str(tmp / "b.pdf"))


def java(cls, body, extra=""):
    return (f"{extra}class {cls} {{\n"
            f"    public static void main(String[] args) {{\n"
            f"        {body}\n"
            f"    }}\n"
            f"}}\n")


CAR = """class Car{
    String brand;
    int speed;
    Car(String brand, int speed){
        this.brand = brand;
        this.speed = speed;
    }
    void show(){
        System.out.println("Brand: " + brand);
        System.out.println("Speed: " + speed);
    }
}
public class CarDemo{
    public static void main(String[] args){
        Car c = new Car("Tata", 120);
        c.show();
    }
}
"""
CIRCLE = """class Circle{
    double r;
    Circle(double r){ this.r = r; }
    double area(){ return 3.14 * r * r; }
}
public class CircleDemo{
    public static void main(String[] args){
        Circle c = new Circle(2);
        System.out.println("Area : " + c.area());
    }
}
"""


# ---------------------------------------------------------------- one file per question
def test_txt_per_question_with_number_line_and_pasted_output(tmp):
    """The real pattern: 'N.' on the first line, the code, then the output pasted below."""
    files = [
        ("OOps Assignment 1 ..KA 1...txt", f"OOps Assignment 1 ..\n1.\n{CAR}\nBrand: Tata\nSpeed: 120\n".encode()),
        ("OOPS ASSI 1 KA 2.txt", f"2..\n{CIRCLE}\nArea : 12.56\n".encode()),
    ]
    _, r = extract(tmp, files)
    assert [p.question for p in r.programs] == ["1", "2"]
    q1, q2 = r.programs
    assert q1.language == "java" and q1.entrypoint == "CarDemo"
    assert "Brand: Tata" not in q1.code and "OOps Assignment" not in q1.code
    assert q1.code.rstrip().endswith("}")
    assert q1.claimed_output == "Brand: Tata\nSpeed: 120"
    assert q2.entrypoint == "CircleDemo" and q2.claimed_output == "Area : 12.56"


def test_a_long_line_in_a_code_file_is_kept_whole(tmp):
    # a 200-character println was cut at the page edge (a real Assignment 5 submission)
    msg = "employee salary with bonus: " + "x" * 160
    src = java("Main", f'System.out.println("{msg}" + 1);')
    _, r = extract(tmp, [("a5q1.java", src.encode())])
    assert f'System.out.println("{msg}" + 1);' in r.programs[0].code


def test_output_marked_by_a_comment(tmp):
    src = CIRCLE + "// OUTPUT..\nArea : 12.56\n"
    _, r = extract(tmp, [("q1.java", src.encode()), ("q2.java", CAR.encode())])
    q1 = r.program("1")
    assert q1.claimed_output == "Area : 12.56" and "OUTPUT" not in q1.code


def test_question_number_from_file_name_in_any_order(tmp):
    files = [("q2.java", java("B", 'System.out.println("two");').encode()),
             ("q1.java", java("A", 'System.out.println("one");').encode()),
             ("ass1q3.java", java("C", 'System.out.println("three");').encode())]
    _, r = extract(tmp, files)
    assert {p.question: p.entrypoint for p in r.programs} == {"2": "B", "1": "A", "3": "C"}
    assert not any(p.label_guessed for p in r.programs)


def test_last_number_in_name_is_the_question(tmp):
    files = [("assn1_1.java", java("A", "int x = 1;").encode()),
             ("assn1_2.java", java("B", "int x = 2;").encode())]
    _, r = extract(tmp, files)
    assert [(p.question, p.entrypoint) for p in r.programs] == [("1", "A"), ("2", "B")]


def test_upload_order_when_names_have_no_usable_number(tmp):
    files = [("StudentDemo.java", java("StudentDemo", "int a = 1;").encode()),
             ("Bank.java", java("Bank", "int b = 2;").encode()),
             ("assignment 1 part.java", java("Third", "int c = 3;").encode())]
    _, r = extract(tmp, files)
    assert [(p.question, p.entrypoint) for p in r.programs] == [("1", "StudentDemo"), ("2", "Bank"), ("3", "Third")]
    assert all(p.label_guessed for p in r.programs) and r.programs[0].source_file == "StudentDemo.java"


def test_java_helper_class_without_main_joins_the_program_using_it(tmp):
    car = "import java.util.*;\n\npublic class Car {\n    String brand = \"Tata\";\n    void show() { System.out.println(brand); }\n}\n"
    demo = ("import java.util.Scanner;\n\npublic class CarDemo {\n    public static void main(String[] a) {\n"
            "        new Car().show();\n    }\n}\n")
    _, r = extract(tmp, [("Car.java", car.encode()), ("CarDemo.java", demo.encode()),
                         ("Other.java", java("Other", "int z = 0;").encode())])
    assert [p.question for p in r.programs] == ["1", "2"]
    p = r.programs[0]
    assert p.entrypoint == "CarDemo" and "class Car" in p.code and "class CarDemo" in p.code
    head = p.code.split("class")[0]
    assert "import java.util.*;" in head and "import java.util.Scanner;" in head
    assert r.programs[1].entrypoint == "Other"


def test_output_file_attaches_to_its_question(tmp):
    files = [("q1.py", b"print(int(input()) * 2)\n"), ("q2.py", b"print(int(input()) + 1)\n"),
             ("output1.txt", b"10\n"), ("q2 output.txt", b"6\n")]
    _, r = extract(tmp, files)
    assert {p.question: p.claimed_output for p in r.programs} == {"1": "10", "2": "6"}


def test_a_file_holding_several_questions_keeps_its_headings(tmp):
    doc = ("Q1\nprint('a')\nprint('b')\nOutput:\na\nb\n\nQ2\nx = int(input())\nprint(x * x)\nOutput:\n9\n")
    _, r = extract(tmp, [("all.txt", doc.encode()), ("extra.py", b"print('c')\nprint('d')\n")])
    assert [p.question for p in r.programs] == ["1", "2", "3"]
    assert r.program("2").claimed_output == "9"


def test_single_file_behaves_as_before(tmp):
    _, r = extract(tmp, [("Main.java", CAR.encode())])
    assert [p.question for p in r.programs] == ["1"] and r.programs[0].entrypoint == "CarDemo"


@needs_office
def test_one_word_file_per_question(tmp):
    pytest.importorskip("docx")
    from docxgen import make_docx
    one = "def double(x):\n    return x * 2\n\nn = int(input())\nprint(double(n))"
    two = "def square(x):\n    return x * x\n\nn = int(input())\nprint(square(n))"
    a = make_docx(tmp / "a.docx", [("p", "Name: Riya"), ("code", one, "Courier New")])
    b = make_docx(tmp / "b.docx", [("p", "Name: Riya"), ("code", two, "Courier New")])
    _, r = extract(tmp, [("Q1.docx", open(a, "rb").read()), ("Q2.docx", open(b, "rb").read())])
    assert [(p.question, p.language) for p in r.programs] == [("1", "python"), ("2", "python")]
    assert "square" in r.program("2").code


@needs_tesseract
def test_output_screenshot_file_named_for_a_question(tmp):
    files = [("q1.py", b"print('hello')\nprint('world')\n"), ("q2.py", b"print(2 + 2)\nprint(3 + 3)\n"),
             ("Q2_output.png", screenshot("$ python q2.py\n4\n6\n$"))]
    _, r = extract(tmp, files)
    q2 = r.program("2")
    assert q2.claimed_from_image and q2.claimed_output.split() == ["4", "6"]
    assert r.program("1").claimed_output is None


# ---------------------------------------------------------------- odd names and encodings
@pytest.mark.parametrize("name", ["Assignment1", "assig_1.javax", "prog.3", "notes.TXT", "Main.JAVA"])
def test_text_files_are_read_whatever_the_extension(name):
    assert sniff(b"public class A { }\n", name) == "text"


def test_windows_text_encodings(tmp):
    utf16 = "class A {\n  // café\n}\n".encode("utf-16")
    cp1252 = "x = 1  # café – note\nprint(x)\n".encode("cp1252")
    assert sniff(utf16, "a.java") == "text" and sniff(cp1252, "b.py") == "text"
    _, r = extract(tmp, [("a.py", cp1252)])
    assert "print(x)" in r.programs[0].code


def test_binary_is_not_text():
    assert sniff(b"\x00\x01\x02binary\xff\xfe", "data.bin") is None
    assert sniff(bytes(range(256)) * 4, "weird") is None


def test_compiled_java_class_file_is_explained():
    with pytest.raises(ConversionError, match=r"compiled.*\.java"):
        to_pdf(b"\xca\xfe\xba\xbe\x00\x00\x00\x41" + b"\x00" * 40, "Car.class")
    b = bundle([("Car.class", b"\xca\xfe\xba\xbe" + b"\x00" * 40), ("Car.java", CAR.encode())])
    assert [p["name"] for p in b.parts] == ["Car.java"] and "Car.class" in b.errors[0]


# ---------------------------------------------------------------- archives
def _zip(members: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for n, d in members.items():
            z.writestr(n, d)
    return buf.getvalue()


def test_zip_is_unpacked_into_its_files(tmp):
    z = _zip({"lab1/q2.py": b"print(2)\nprint(22)\n", "lab1/q1.py": b"print(1)\nprint(11)\n",
              "__MACOSX/lab1/._q1.py": b"\x00\x05junk", "lab1/.DS_Store": b"\x00\x00",
              "lab1/q1.class": b"\xca\xfe\xba\xbe\x00"})
    b, r = extract(tmp, [("lab1.zip", z)])
    assert [p["name"] for p in b.parts] == ["lab1.zip/lab1/q1.py", "lab1.zip/lab1/q2.py"]
    assert {p.question: p.code.split()[0] for p in r.programs} == {"1": "print(1)", "2": "print(2)"}
    assert any("q1.class" in e for e in b.errors)


def test_zip_limits():
    bomb = _zip({f"f{i}.txt": b"a" for i in range(500)})
    assert len(expand([("many.zip", bomb)])) <= 101
    with pytest.raises(ConversionError):
        to_pdf(_zip({"x.txt": b"0" * (60 * 1024 * 1024)}), "big.zip")


def test_nested_zip_is_not_unpacked_twice():
    inner = _zip({"a.py": b"print(1)\n"})
    out = expand([("outer.zip", _zip({"inner.zip": inner, "b.py": b"print(2)\n"}))])
    assert [n for n, _ in out] == ["outer.zip/b.py", "outer.zip/inner.zip"]


# ---------------------------------------------------------------- notebooks
def _nb(cells):
    return json.dumps({"nbformat": 4, "nbformat_minor": 5, "metadata": {}, "cells": cells}).encode()


def test_jupyter_notebook_code_and_outputs(tmp):
    nb = _nb([
        {"cell_type": "markdown", "source": ["## Q1 Square a number"]},
        {"cell_type": "code", "source": ["n = int(input())\n", "print(n * n)"],
         "outputs": [{"output_type": "stream", "name": "stdout", "text": ["9\n"]}]},
        {"cell_type": "markdown", "source": "## Q2"},
        {"cell_type": "code", "source": "for i in range(3):\n    print(i)",
         "outputs": [{"output_type": "execute_result", "data": {"text/plain": ["0\n1\n2"]}}]},
    ])
    assert sniff(nb, "lab.ipynb") == "notebook"
    b, r = extract(tmp, [("lab.ipynb", nb)])
    assert b.parts[0]["kind"] == "notebook"
    assert [p.question for p in r.programs] == ["1", "2"]
    assert r.program("1").claimed_output == "9" and "print(n * n)" in r.program("1").code
    assert r.program("2").code.splitlines() == ["for i in range(3):", "    print(i)"]


# ---------------------------------------------------------------- more document and photo types
def test_powerpoint_and_excel_are_office_files():
    assert sniff(_zip({"ppt/presentation.xml": b"<p/>"}), "slides.pptx") == "office"
    assert sniff(_zip({"xl/workbook.xml": b"<w/>"}), "marks.xlsx") == "office"
    assert sniff(_zip({"a.py": b"print(1)"}), "code.zip") == "zip"


def test_iphone_heic_photo(tmp):
    heif = pytest.importorskip("pillow_heif")
    from PIL import Image
    buf = io.BytesIO()
    heif.from_pillow(Image.open(io.BytesIO(screenshot("Sum = 7", dark=False)))).save(buf, quality=95)
    data = buf.getvalue()
    assert sniff(data, "IMG_0042.HEIC") == "image"
    pdf, kind = to_pdf(data, "IMG_0042.HEIC")
    assert kind == "image" and pdf.startswith(b"%PDF")


# ---------------------------------------------------------------- code files next to a full document
STUDENT = """class Student{
    String name; int roll;
    Student(String name, int roll){ this.name = name; this.roll = roll; }
    void display(){ System.out.println("Name: " + name + " Roll: " + roll); }
}
public class StudentDemo{
    public static void main(String[] args){
        Student s = new Student("Asha", 7);
        s.display();
    }
}
"""


def test_code_files_take_their_number_from_the_document_with_all_questions(tmp):
    """The common real case: q-files (or files named after classes) AND a PDF/Word file
    holding every question. The document numbers the answers; the code files give
    the exact code; the document gives the output the student showed."""
    from pdfgen import make_pdf
    doc = make_pdf(tmp / "all.pdf", [
        ("h", "Question 1"), ("code", CAR, "mono_offset"), ("p", "Output:"), ("p", "Brand: Tata"),
        ("h", "Question 2"), ("code", STUDENT, "mono_offset"), ("p", "Output:"), ("p", "Name: Asha Roll: 7"),
        ("h", "Question 3"), ("code", CIRCLE, "mono_offset"), ("p", "Output:"), ("p", "Area : 12.56"),
    ])
    files = [("Circle.java", CIRCLE.encode()), ("StudentDemo.java", STUDENT.encode()),
             ("CarDemo.java", CAR.encode()), ("Assignment 1.pdf", open(doc, "rb").read())]
    _, r = extract(tmp, files)
    assert sorted(p.question for p in r.programs) == ["1", "2", "3"]
    assert {p.question: p.entrypoint for p in r.programs} == {"1": "CarDemo", "2": "StudentDemo", "3": "CircleDemo"}
    assert r.program("2").claimed_output == "Name: Asha Roll: 7"
    assert r.program("3").code == CIRCLE    # the code file's exact text


def test_the_same_code_uploaded_twice_counts_once(tmp):
    files = [("assig_1.java", CAR.encode()), ("assig_1.javax", CAR.encode()),
             ("assig_2.java", CIRCLE.encode())]
    _, r = extract(tmp, files)
    assert [(p.question, p.entrypoint) for p in r.programs] == [("1", "CarDemo"), ("2", "CircleDemo")]


@needs_tesseract
def test_screenshot_named_after_a_code_file(tmp):
    files = [("Circle.java", CIRCLE.encode()), ("CarDemo.java", CAR.encode()),
             ("CarDemo.png", screenshot("Brand: Tata\nSpeed: 120"))]
    _, r = extract(tmp, files)
    car = next(p for p in r.programs if p.entrypoint == "CarDemo")
    assert car.claimed_from_image and "Speed: 120" in car.claimed_output
    assert next(p for p in r.programs if p.entrypoint == "CircleDemo").claimed_output is None


def test_document_with_a_different_version_of_each_answer(tmp):
    """Real case: the PDF report has a cleaned-up version of each program and the
    .java files an older one. Each file still takes its question's number, the version
    that comes with its shown output is graded, and the difference is flagged."""
    from pdfgen import make_pdf
    car_v2 = CAR.replace("brand", "carBrand").replace("speed", "topSpeed").replace("show", "printDetails")
    stu_v2 = STUDENT.replace("roll", "rollNumber").replace("display", "showInfo").replace("Asha", "Ravi")
    doc = make_pdf(tmp / "all.pdf", [
        ("h", "Q1) Create a class Car"), ("code", car_v2, "mono_offset"), ("p", "Output:"), ("p", "Brand: Tata"),
        ("h", "Q2) Design a class Student"), ("code", stu_v2, "mono_offset"), ("p", "Output:"), ("p", "Name: Ravi Roll: 7"),
    ])
    files = [("ass1q2.java", STUDENT.encode()), ("assiq1.java", CAR.encode()),
             ("Assignment 1.pdf", open(doc, "rb").read())]
    _, r = extract(tmp, files)
    assert [p.question for p in r.programs] == ["1", "2"]
    q2 = r.program("2")
    assert "rollNumber" in q2.code and q2.claimed_output == "Name: Ravi Roll: 7"
    assert q2.needs_review and any("different version" in w for w in q2.warnings)


def test_stray_heading_inside_a_one_question_file_does_not_split_it(tmp):
    """Real case: one scanned PDF per question, where OCR read a stray 'Q14' mid-page.
    A file is only a multi-question document if it has two different real headings."""
    from pdfgen import make_pdf
    first, rest = CAR.split("public class CarDemo")
    a = make_pdf(tmp / "a.pdf", [("code", first, "mono_offset"), ("h", "Q14"),
                                 ("code", "public class CarDemo" + rest, "mono_offset")])
    b = make_pdf(tmp / "b.pdf", [("code", CIRCLE, "mono_offset")])
    _, r = extract(tmp, [("Assignment1Q1", open(a, "rb").read()), ("Assignment1Q2", open(b, "rb").read())])
    assert [(p.question, p.entrypoint) for p in r.programs] == [("1", "CarDemo"), ("2", "CircleDemo")]
    assert "class Car" in r.program("1").code


def test_question_numbers_are_never_used_twice(tmp):
    files = [("q1.py", b"print(int(input()) * 2)\nprint('done')\n"),
             ("q1 again.py", b"x = int(input())\nprint(x ** 3)\n"),
             ("other.py", b"for i in range(3):\n    print(i)\n")]
    _, r = extract(tmp, files)
    labels = [p.question for p in r.programs]
    assert len(labels) == len(set(labels)) == 3


@needs_tesseract
def test_photo_of_the_code_next_to_the_code_file(tmp):
    """Real case: six .java files plus a phone photo of each program."""
    files = [("Circle.java", CIRCLE.encode()), ("CarDemo.java", CAR.encode()),
             ("IMG-20260810-WA0192.jpg", screenshot(CIRCLE, dark=False, title=None, font_px=18)),
             ("IMG-20260810-WA0193.jpg", screenshot(CAR, dark=False, title=None, font_px=18))]
    _, r = extract(tmp, files)
    assert [(p.question, p.entrypoint) for p in r.programs] == [("1", "CircleDemo"), ("2", "CarDemo")]
    assert not r.program("1").ocr           # the code file's exact text is graded


@needs_office
def test_word_file_with_damaged_pictures_is_salvaged(tmp):
    """Real case: an upload where every picture inside the .docx failed its checksum.
    LibreOffice refuses the file; the text is still read and the damage reported."""
    pytest.importorskip("docx")
    from docxgen import make_docx
    path = make_docx(tmp / "lab.docx", [("h", "Question 1"), ("code", CIRCLE, "Courier New"),
                                        ("img", screenshot("Area : 12.56", dark=False))])
    src = zipfile.ZipFile(path)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as z:     # stored, so bytes can be flipped below
        for n in src.namelist():
            z.writestr(n, src.read(n))
    raw = bytearray(buf.getvalue())
    png = raw.find(b"\x89PNG")
    raw[png + 200:png + 260] = b"\x00" * 60                          # damage the picture, keep its checksum
    notes = []
    pdf, kind = to_pdf(bytes(raw), "Assignment 1.docx", notes)
    assert kind == "office" and pdf.startswith(b"%PDF")
    assert notes and "damaged" in notes[0]
    b = bundle([("Assignment 1.docx", bytes(raw))])
    assert [p["name"] for p in b.parts] == ["Assignment 1.docx"] and "damaged" in b.errors[0]


def test_ligature_letters_keep_their_order():
    """Real case: Word set "ti" in "Question" as one glyph; its zero-width 'i' sat at
    the same x as the next letter and the heading came out as "Questoi  n 1:".
    Character boxes copied from the student's file, in the order the PDF lists them."""
    from docextract.pdfread import _build_line
    boxes = [("Q", 72.1, 83.1), ("u", 83.0, 91.6), ("e", 91.6, 99.7), ("s", 99.7, 106.1),
             ("t", 106.1, 115.41), ("i", 115.41, 115.41), ("o", 115.39, 124.0), ("n", 124.0, 132.6),
             (" ", 132.6, 136.2), ("1", 136.2, 144.3), (":", 144.3, 148.7)]
    chars = [(c, x0, x1, 100.0, 14.0, "Carlito-Bold", 72.1, i) for i, (c, x0, x1) in enumerate(boxes)]
    assert _build_line(chars, 1, 842).text == "Question 1:"


@needs_tesseract
def test_partial_photo_of_code_matches_its_file(tmp):
    """Real case: phone photos that show only part of each program (and OCR misreads
    some of it) still belong to the .java file they show, by name or by best match."""
    top_of = lambda code: "\n".join(code.splitlines()[:6])
    files = [("Circle.java", CIRCLE.encode()), ("Car.java", CAR.encode()), ("Student.java", STUDENT.encode()),
             ("IMG-20260810-WA0192.jpg", screenshot(top_of(STUDENT), dark=False, title=None, font_px=18)),
             ("Circle.png", screenshot(top_of(CIRCLE), dark=False, title=None, font_px=18)),
             ("IMG-20260810-WA0193.jpg", screenshot(top_of(CAR), dark=False, title=None, font_px=18))]
    _, r = extract(tmp, files)
    assert [(p.question, p.entrypoint) for p in r.programs] == [("1", "CircleDemo"), ("2", "CarDemo"), ("3", "StudentDemo")]
    assert not any(p.ocr for p in r.programs)
