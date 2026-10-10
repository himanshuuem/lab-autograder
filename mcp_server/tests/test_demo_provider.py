import pymupdf
import pytest

from classroom_mcp.demo_provider import DemoProvider
from classroom_mcp.provider import ProviderError


@pytest.fixture(scope="module")
def p():
    return DemoProvider()


def test_courses_and_coursework(p):
    (c,) = p.list_courses()
    (cw,) = p.list_coursework(c["id"])
    assert cw["max_points"] == 20 and cw["materials"][0]["file_id"] == "f-assignment3"
    with pytest.raises(ProviderError):
        p.list_coursework("nope")


def test_submissions(p):
    subs = p.list_submissions("demo-it2271", "cw-lab3")
    assert len(subs) == 11
    missing = [s for s in subs if not s["files"]]
    assert len(missing) == 1 and missing[0]["state"] == "CREATED"
    assert all(s["student"]["email"].endswith("iiests.ac.in") for s in subs)


def test_download_pdfs(p):
    f = p.download_file("f-s01")
    assert f["data"].startswith(b"%PDF") and f["mime"] == "application/pdf"
    doc = pymupdf.open(stream=f["data"], filetype="pdf")
    assert "Bubble sort" in doc[0].get_text()
    scan = pymupdf.open(stream=p.download_file("f-s08")["data"], filetype="pdf")
    assert scan[0].get_text().strip() == "" and scan[0].get_images()
    with pytest.raises(ProviderError):
        p.download_file("missing")


def test_word_and_screenshot_students(p):
    subs = {s["student"]["name"]: s for s in p.list_submissions("demo-it2271", "cw-lab3")}
    riya = subs["Riya Sen"]["files"]
    assert [f["title"] for f in riya] == ["Riya_Sen_Lab3.docx"]
    f = p.download_file(riya[0]["file_id"])
    assert f["data"][:2] == b"PK" and f["mime"].endswith("wordprocessingml.document")
    aman = subs["Aman Gupta"]["files"]
    assert [x["title"] for x in aman] == ["2023ITB011_Aman_Gupta.pdf", "Q2_output.png"]
    assert p.download_file(aman[1]["file_id"])["data"].startswith(b"\x89PNG")


def test_set_grade(p):
    p.set_grade("demo-it2271", "cw-lab3", "sub-s01", 18, False)
    s = next(x for x in p.list_submissions("demo-it2271", "cw-lab3") if x["id"] == "sub-s01")
    assert s["draft_grade"] == 18 and s["assigned_grade"] is None
