"""Screenshots inside submissions, and submissions that aren't PDFs."""
import shutil
import zipfile
import io

import pymupdf
import pytest
from conftest import needs_tesseract, run_program
from pdfgen import make_pdf, screenshot
from samples import C_SUM, JAVA_REV, PY_FACT

from docextract import ConversionError, bundle, extract_submission, sniff, to_pdf
from docextract.cleanup import is_terminal_noise
from docextract.pdfread import read_pdf

needs_office = pytest.mark.skipif(shutil.which("soffice") is None, reason="LibreOffice not installed")
needs_docx = pytest.importorskip


# ---------------------------------------------------------------- screenshots in PDFs
@needs_tesseract
def test_output_screenshot_under_label(tmp):
    pdf = make_pdf(tmp / "s.pdf", [("h", "Question 1"), ("p", "Code:"), ("code", C_SUM, "mono_offset"),
                                   ("p", "Output:"), ("img", screenshot("$ ./a.out\n3 4\nSum = 7\n$"))])
    p = extract_submission(pdf).programs[0]
    assert p.claimed_from_image and "Sum = 7" in p.claimed_output
    assert "a.out" not in p.claimed_output and "Terminal" not in p.claimed_output
    assert not p.ocr and not p.needs_review          # the typed code is not OCR'd


@needs_tesseract
def test_unlabelled_screenshot_after_code_is_output(tmp):
    shot = screenshot('"C:\\Program Files\\Java\\jdk-21\\bin\\java.exe" ReverseString\nhello\nReversed: olleh\n\n'
                      "Process finished with exit code 0", dark=False, title="Run: ReverseString")
    pdf = make_pdf(tmp / "s.pdf", [("h", "Q1"), ("code", JAVA_REV, "mono_offset"), ("img", shot)])
    p = extract_submission(pdf).programs[0]
    assert p.claimed_from_image
    assert p.claimed_output.splitlines()[-1].endswith("olleh")
    assert "Process finished" not in p.claimed_output and "java.exe" not in p.claimed_output
    assert run_program(p.code, "java", "abc\n", p.entrypoint) == "Reversed: cba\n"


@needs_tesseract
def test_code_screenshot_counts_as_code_and_needs_review(tmp):
    code = 'n = int(input())\nfor i in range(n):\n    print(i * i)'
    pdf = make_pdf(tmp / "s.pdf", [("h", "Question 1"), ("p", "Code:"),
                                   ("img", screenshot(code, dark=False, title=None, font_px=18))])
    p = extract_submission(pdf).programs[0]
    assert p.language == "python" and p.ocr and p.needs_review
    assert "range" in p.code


@needs_tesseract
def test_screenshot_alone_on_a_page_is_not_a_scan(tmp):
    pdf = make_pdf(tmp / "s.pdf", [("h", "Q1"), ("code", C_SUM, "mono_offset"), ("pagebreak",),
                                   ("img", screenshot("3 4\nSum = 7"), 200)])
    r = extract_submission(pdf)
    assert r.ocr_pages == [] and r.images_read == 1
    assert "Sum = 7" in r.programs[0].claimed_output


def test_small_images_are_ignored(tmp):
    logo = screenshot("IIEST", title=None)
    pdf = make_pdf(tmp / "s.pdf", [("img", logo, 40), ("h", "Q1"), ("code", C_SUM, "mono_offset")])
    assert read_pdf(pdf).images_read == 0


def test_ocr_never_reads_no_images(tmp):
    pdf = make_pdf(tmp / "s.pdf", [("h", "Q1"), ("code", C_SUM, "mono_offset"), ("p", "Output:"),
                                   ("img", screenshot("Sum = 7"))])
    assert read_pdf(pdf, ocr="never").images_read == 0


@pytest.mark.parametrize("line,noise", [
    ("$ ./a.out", True), ("¢ ./a.out", True), ("C:\\Users\\riya\\lab> java Main", True),
    ("PS C:\\code> python lab.py", True), ("riya@mac lab % ./a.out", True), ("$", True),
    ("Process finished with exit code 0", True), ("...Program finished with exit code 0", True),
    ("Press ENTER to exit console.", True), ("Run: Main", True), ("javac Main.java", True),
    ("Sum = 7", False), ("1 2 3 4 9", False), ("Enter n: 5", False), ("Output: 10", False),
    ("Area of circle: 12.57", False), ("python is fun", False), ("Reversed: dlrow olleh", False),
])
def test_terminal_noise(line, noise):
    assert is_terminal_noise(line) is noise


# ---------------------------------------------------------------- conversion
def test_sniff_by_content_not_name(tmp):
    pdf = (tmp / "x.pdf")
    make_pdf(pdf, [("p", "hi")])
    assert sniff(pdf.read_bytes(), "renamed.docx") == "pdf"
    assert sniff(screenshot("x"), "photo.pdf") == "image"
    assert sniff(b"int main(){}", "main.c") == "text"
    assert sniff(b"\x00\x01binary", "a.exe") is None
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("word/document.xml", "<w/>")
    assert sniff(buf.getvalue(), "lab.docx") == "office"


@needs_tesseract
def test_standalone_image_attachment_becomes_output(tmp):
    pdf = make_pdf(tmp / "s.pdf", [("h", "Question 1"), ("p", "Code:"), ("code", C_SUM, "mono_offset")])
    b = bundle([("lab.pdf", open(pdf, "rb").read()), ("output.png", screenshot("3 4\nSum = 7"))])
    assert [p["kind"] for p in b.parts] == ["pdf", "image"] and not b.errors
    (tmp / "b.pdf").write_bytes(b.pdf)
    p = extract_submission(str(tmp / "b.pdf")).programs[0]
    assert p.claimed_from_image and "Sum = 7" in p.claimed_output
    assert "Attached file" not in p.claimed_output


def test_code_file_attachment(tmp):
    b = bundle([("Main.java", JAVA_REV.encode()), ("output.txt", b"Reversed: cba\n")])
    (tmp / "b.pdf").write_bytes(b.pdf)
    p = extract_submission(str(tmp / "b.pdf")).programs[0]
    assert p.language == "java" and p.claimed_output == "Reversed: cba"
    assert run_program(p.code, "java", "abc\n", p.entrypoint) == "Reversed: cba\n"


def test_unsupported_and_partial(tmp):
    pdf = make_pdf(tmp / "s.pdf", [("h", "Q1"), ("code", C_SUM, "mono_offset")])
    b = bundle([("lab.pdf", open(pdf, "rb").read()), ("project.zip", b"PK\x03\x04garbage"),
                ("big.bin", b"\x00" * 10)])
    assert [p["name"] for p in b.parts] == ["lab.pdf"] and len(b.errors) == 2
    assert bundle([("x.zip", b"PK\x03\x04")]).pdf is None
    with pytest.raises(ConversionError):
        to_pdf(b"%PDF-" + b"0" * (26 * 1024 * 1024), "huge.pdf")


@needs_office
@needs_tesseract
def test_word_submission_end_to_end(tmp):
    pytest.importorskip("docx")
    from docxgen import make_docx
    py_word = PY_FACT.replace('"Fact"', "\u201cFact\u201d").replace("    print(", "    Print(")
    path = make_docx(tmp / "lab.docx", [
        ("p", "Name: Riya Sen"),
        ("h", "Question 1: Sum"), ("p", "Code:"), ("code", C_SUM, "Courier New"),
        ("p", "Output:"), ("img", screenshot("$ ./a.out\n3 4\nSum = 7", dark=True)),
        ("h", "Question 2: Factorials"), ("code", py_word, "Calibri"),
        ("img", screenshot("3\nFact 1 1\nFact 2 2\nFact 3 6\n\nProcess finished with exit code 0",
                           dark=False, title="Run: main"), 3.5),
    ])
    b = bundle([("Riya_Sen_lab.docx", open(path, "rb").read())])
    assert b.parts[0]["kind"] == "office" and not b.errors
    (tmp / "b.pdf").write_bytes(b.pdf)
    r = extract_submission(str(tmp / "b.pdf"))
    q1, q2 = r.programs
    assert q1.language == "c" and run_program(q1.code, "c", "3 4\n") == "Sum = 7\n"
    assert "Sum = 7" in q1.claimed_output and q1.claimed_from_image
    assert q2.language == "python" and q2.repairs.get("auto_capital_fixed") == 1
    assert run_program(q2.code, "python", "2\n") == "Fact 1 1\nFact 2 2\n"
    assert q2.claimed_from_image and "Fact 3 6" in q2.claimed_output
    assert r.ocr_pages == []
