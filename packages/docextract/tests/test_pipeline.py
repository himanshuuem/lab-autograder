"""End-to-end: build a realistic PDF, extract, then compile and RUN the extracted code."""
import pytest
from conftest import needs_tesseract, run_program
from pdfgen import make_outlined, make_pdf, make_scanned
from samples import CASES, C_SUM, JAVA_REV, PY_FACT, PY_CLASS

from docextract import extract_submission

STYLES = ["mono_spaces", "mono_offset", "prop_offset", "numbered"]


def submission(path, code, style, title="Question 1: Program", output="see below"):
    return make_pdf(path, [
        ("p", "Name: Rahul Das    Roll No: 2023ITB045"),
        ("h", title),
        ("p", "Write a program for the problem given in class and show the output."),
        ("p", "Code:"),
        ("code", code, style),
        ("p", "Output:"),
        ("code", output, "mono_spaces"),
    ], header="2023ITB045 - Rahul Das")


@pytest.mark.parametrize("style", STYLES)
@pytest.mark.parametrize("case", list(CASES))
def test_extracted_code_runs_correctly(tmp, case, style):
    code, lang, stdin, expected, entry = CASES[case]
    res = extract_submission(submission(tmp / "s.pdf", code, style))
    assert len(res.programs) == 1
    p = res.programs[0]
    assert p.language == lang
    assert p.entrypoint == entry
    assert not p.needs_review, p.warnings
    assert run_program(p.code, lang, stdin, entry) == expected


@pytest.mark.parametrize("style", ["mono_spaces", "mono_offset"])
def test_monospace_code_is_reproduced_exactly(tmp, style):
    res = extract_submission(submission(tmp / "s.pdf", PY_CLASS, style))
    assert res.programs[0].code == PY_CLASS + "\n"


def test_claimed_output_is_captured(tmp):
    res = extract_submission(submission(tmp / "s.pdf", PY_FACT, "mono_offset",
                                        output="Fact 1 1\nFact 2 2\nFact 3 6"))
    assert res.programs[0].claimed_output == "Fact 1 1\nFact 2 2\nFact 3 6"


def test_inline_output_label(tmp):
    pdf = make_pdf(tmp / "s.pdf", [("h", "Q1"), ("code", C_SUM, "mono_offset"),
                                   ("p", "Output: Sum = 7")])
    assert extract_submission(pdf).programs[0].claimed_output == "Sum = 7"


def test_missing_output_section_is_warned(tmp):
    pdf = make_pdf(tmp / "s.pdf", [("h", "Q1"), ("code", C_SUM, "mono_offset")])
    p = extract_submission(pdf).programs[0]
    assert p.claimed_output is None
    assert any("Output" in w for w in p.warnings)


def test_several_questions_in_one_pdf(tmp):
    pdf = make_pdf(tmp / "s.pdf", [
        ("p", "Name: Priya Sen"),
        ("h", "Q1. Factorial"), ("p", "Code:"), ("code", PY_FACT, "mono_offset"),
        ("p", "Output:"), ("code", "Fact 1 1", "mono_spaces"),
        ("h", "Ques 2: Sum"), ("code", C_SUM, "prop_offset"), ("p", "Output: Sum = 7"),
        ("pagebreak",),
        ("h", "Question 3 - Reverse"), ("code", JAVA_REV, "mono_spaces"),
        ("p", "Sample Output:"), ("code", "Reversed: cba", "mono_spaces"),
    ])
    res = extract_submission(pdf)
    assert [(p.question, p.language) for p in res.programs] == [
        ("1", "python"), ("2", "c"), ("3", "java")]
    assert res.program("2").claimed_output == "Sum = 7"
    assert res.program("3").claimed_output == "Reversed: cba"
    assert run_program(res.program("3").code, "java", "xy\n", "ReverseString") == "Reversed: yx\n"


def test_word_processor_damage_is_repaired_and_reported(tmp):
    damaged = (PY_FACT.replace('"Fact"', "\u201cFact\u201d")
                      .replace("n - 1", "n \u2212 1")
                      .replace("def fact", "Def fact")
                      .replace("for i", "For i")
                      .replace("print(", "Print(")
                      .replace("return 1", "return\u00a01"))
    res = extract_submission(submission(tmp / "s.pdf", damaged, "mono_offset"))
    p = res.programs[0]
    assert run_program(p.code, "python", "3\n") == "Fact 1 1\nFact 2 2\nFact 3 6\n"
    assert p.repairs["auto_capital_fixed"] == 3
    assert res.repairs["smart_quote"] == 2
    assert res.repairs["dash"] == 1


def test_autocapitalised_c_is_repaired(tmp):
    damaged = C_SUM.replace("int main", "Int main").replace("    return", "    Return")
    p = extract_submission(submission(tmp / "s.pdf", damaged, "mono_offset")).programs[0]
    assert run_program(p.code, "c", "1 2\n") == "Sum = 3\n"


def test_code_across_pages_with_repeated_header(tmp):
    long_code = PY_FACT + "\n" + "\n".join(f"x{i} = {i}" for i in range(60)) + "\nprint(x59)"
    pdf = make_pdf(tmp / "s.pdf", [("h", "Q1"), ("code", long_code, "mono_offset")],
                   header="2023ITB045 - Rahul Das")
    res = extract_submission(pdf)
    p = res.programs[0]
    assert "Rahul" not in p.code and "Page" not in p.code
    assert res.repairs["header_footer_removed"] >= 4
    assert p.pages == [1, 2]
    assert run_program(p.code, "python", "2\n").endswith("59\n")


def test_prose_between_code_is_excluded(tmp):
    pdf = make_pdf(tmp / "s.pdf", [
        ("h", "Q1"),
        ("code", PY_FACT.split("\n\n\n")[0], "mono_offset"),
        ("p", "The function above computes the factorial of a number using recursion."),
        ("code", PY_FACT.split("\n\n\n")[1], "mono_offset"),
    ])
    p = extract_submission(pdf).programs[0]
    assert "recursion" not in p.code
    assert any("2 separate code blocks" in w for w in p.warnings)
    assert run_program(p.code, "python", "2\n") == "Fact 1 1\nFact 2 2\n"


def test_no_question_headings_gives_one_program(tmp):
    pdf = make_pdf(tmp / "s.pdf", [("p", "Name: A"), ("code", C_SUM, "mono_offset")])
    res = extract_submission(pdf)
    assert len(res.programs) == 1 and res.programs[0].language == "c"


def test_pdf_without_code_needs_review(tmp):
    pdf = make_pdf(tmp / "s.pdf", [("h", "Assignment 1"),
                                   ("p", "I could not complete this assignment because I was ill.")])
    res = extract_submission(pdf)
    assert res.programs == [] and res.needs_review
    assert any("no code" in w for w in res.warnings)


def test_broken_python_is_flagged_not_hidden(tmp):
    broken = "def f(x)\n    return x\nprint(f(2))"
    p = extract_submission(submission(tmp / "s.pdf", broken, "mono_offset")).programs[0]
    assert p.needs_review
    assert any("syntax error" in w for w in p.warnings)


def test_not_a_pdf_raises(tmp):
    bad = tmp / "x.pdf"
    bad.write_bytes(b"this is not a pdf")
    with pytest.raises(ValueError):
        extract_submission(str(bad))


def test_to_dict_is_json_serialisable(tmp):
    import json
    res = extract_submission(submission(tmp / "s.pdf", C_SUM, "mono_offset"))
    d = json.loads(json.dumps(res.to_dict()))
    assert d["programs"][0]["language"] == "c" and "needs_review" in d


@needs_tesseract
def test_scanned_pdf_uses_ocr_and_always_needs_review(tmp):
    text_pdf = make_pdf(tmp / "t.pdf", [
        ("h", "Question 1"), ("code", C_SUM, "mono_spaces"), ("p", "Output: Sum = 7")])
    res = extract_submission(make_scanned(text_pdf, tmp / "scan.pdf", dpi=300))
    assert res.ocr_pages == [1]
    p = res.programs[0]
    assert p.language == "c" and p.ocr
    assert p.needs_review
    assert "scanf" in p.code and "printf" in p.code
    assert p.claimed_output == "Sum = 7"


@needs_tesseract
def test_text_drawn_as_vector_shapes_is_read_by_ocr(tmp):
    # two real Assignment 5 PDFs: typed code, but every letter a vector path (no text layer)
    text_pdf = make_pdf(tmp / "t.pdf", [
        ("h", "Question 1"), ("code", C_SUM, "mono_spaces"), ("p", "Output: Sum = 7")])
    res = extract_submission(make_outlined(text_pdf, tmp / "outlined.pdf"))
    assert res.ocr_pages == [1]
    p = res.programs[0]
    assert p.language == "c" and p.ocr and p.needs_review
    assert "scanf" in p.code and "printf" in p.code


def test_ocr_never_skips_scans(tmp):
    text_pdf = make_pdf(tmp / "t.pdf", [("h", "Q1"), ("code", C_SUM, "mono_spaces")])
    res = extract_submission(make_scanned(text_pdf, tmp / "scan.pdf"), ocr="never")
    assert res.programs == [] and res.ocr_pages == []
