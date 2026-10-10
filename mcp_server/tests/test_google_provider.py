"""GoogleProvider against fake Classroom/Drive services (no network)."""
import pytest
from googleapiclient.errors import HttpError
from httplib2 import Response

from classroom_mcp.google_provider import GoogleProvider


class Call:
    def __init__(self, result):
        self.result = result

    def execute(self):
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class Pager:
    """Mimics a `.list(**kw)` method that pages with pageToken."""
    def __init__(self, pages, log):
        self.pages, self.log = pages, log

    def __call__(self, **kw):
        self.log.append(kw)
        i = int(kw.get("pageToken") or 0)
        res = dict(self.pages[i])
        if i + 1 < len(self.pages):
            res["nextPageToken"] = str(i + 1)
        return Call(res)


class FakeClassroom:
    def __init__(self):
        self.log, self.patches = [], []
        self.patch_error = None
        outer = self

        class Subs:
            list = Pager([{"studentSubmissions": [
                {"id": "a", "userId": "u1", "state": "TURNED_IN", "late": True,
                 "assignmentSubmission": {"attachments": [{"driveFile": {"id": "d1", "title": "a.pdf"}}]}}]},
                {"studentSubmissions": [{"id": "b", "userId": "u9", "state": "CREATED"}]}], self.log)

            def patch(self, **kw):
                outer.patches.append(kw)
                return Call(outer.patch_error or {})

        class CourseWork:
            list = Pager([{"courseWork": [
                {"id": "w1", "title": "Lab 1", "maxPoints": 10, "workType": "ASSIGNMENT",
                 "dueDate": {"year": 2026, "month": 9, "day": 5},
                 "materials": [{"driveFile": {"driveFile": {"id": "m1", "title": "q.pdf"}}}]},
                {"id": "w2", "title": "Quiz", "workType": "MULTIPLE_CHOICE_QUESTION"}]}], self.log)

            def studentSubmissions(self):
                return Subs()

        class Students:
            list = Pager([{"students": [{"userId": "u1", "profile": {
                "name": {"fullName": "Ananya Bose"}, "emailAddress": "a@x.in"}}]}], self.log)

        class Courses:
            list = Pager([{"courses": [{"id": "c1", "name": "DS Lab"}]},
                          {"courses": [{"id": "c2", "name": "OOP Lab", "section": "B"}]}], self.log)

            def courseWork(self):
                return CourseWork()

            def students(self):
                return Students()

        self._courses = Courses()

    def courses(self):
        return self._courses


class FakeDrive:
    def __init__(self, mime):
        self.mime, self.calls = mime, []
        outer = self

        class Files:
            def get(self, **kw):
                return Call({"id": kw["fileId"], "name": "sub.pdf", "mimeType": outer.mime, "size": "10"})

            def export_media(self, **kw):
                outer.calls.append(("export", kw))
                return "EXPORT"

            def get_media(self, **kw):
                outer.calls.append(("media", kw))
                return "MEDIA"

        self._files = Files()

    def files(self):
        return self._files


def provider(mime="application/pdf"):
    p = GoogleProvider(token_file="/nonexistent", classroom=FakeClassroom(), drive=FakeDrive(mime))
    p._fetch = lambda req: f"%PDF {req}".encode()
    return p


def test_courses_paginate():
    p = provider()
    assert [c["id"] for c in p.list_courses()] == ["c1", "c2"]
    assert p.classroom.log[0]["teacherId"] == "me"


def test_coursework_keeps_assignments_only():
    (w,) = provider().list_coursework("c1")
    assert w["due"] == "2026-09-05" and w["materials"][0]["file_id"] == "m1"


def test_submissions_join_roster():
    subs = provider().list_submissions("c1", "w1")
    assert subs[0]["student"]["name"] == "Ananya Bose" and subs[0]["late"]
    assert subs[0]["files"] == [{"file_id": "d1", "title": "a.pdf", "link": ""}]
    assert subs[1]["student"]["name"] == "u9" and subs[1]["files"] == []


def test_google_doc_is_exported_as_pdf():
    p = provider("application/vnd.google-apps.document")
    f = p.download_file("d1")
    assert f["mime"] == "application/pdf" and f["data"] == b"%PDF EXPORT"
    assert p.drive.calls[0][1]["mimeType"] == "application/pdf"


def test_regular_file_downloaded():
    assert provider().download_file("d1")["data"] == b"%PDF MEDIA"


@pytest.mark.parametrize("kind", ["presentation", "spreadsheet", "drawing"])
def test_other_google_formats_exported(kind):
    f = provider(f"application/vnd.google-apps.{kind}").download_file("d1")
    assert f["mime"] == "application/pdf" and f["data"] == b"%PDF EXPORT"


def test_unexportable_google_types_refused():
    from classroom_mcp.provider import ProviderError
    with pytest.raises(ProviderError):
        provider("application/vnd.google-apps.form").download_file("d1")


def test_set_grade_masks():
    p = provider()
    assert p.set_grade("c1", "w1", "a", 8.5, assign=True) == {"ok": True}
    kw = p.classroom.patches[0]
    assert kw["updateMask"] == "draftGrade,assignedGrade" and kw["body"]["assignedGrade"] == 8.5


def test_set_grade_403_explains():
    p = provider()
    p.classroom.patch_error = HttpError(Response({"status": "403"}), b"forbidden")
    r = p.set_grade("c1", "w1", "a", 5, assign=False)
    assert not r["ok"] and "CSV" in r["error"]


def test_missing_token_message():
    from classroom_mcp.provider import ProviderError
    with pytest.raises(ProviderError, match="google_auth.py"):
        GoogleProvider(token_file="/nonexistent").list_courses()
