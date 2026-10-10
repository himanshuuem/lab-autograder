"""Real Google Classroom + Drive.

Auth, either:
- the signed-in teacher's access token, sent by the dashboard with each request
  (X-Google-Access-Token; the dashboard keeps and refreshes each teacher's grant), or
- an OAuth user token (token.json) made once with scripts/google_auth.py, for a
  single-teacher setup.
"""
from __future__ import annotations

import io
import logging
import os

from .provider import Provider, ProviderError

log = logging.getLogger("classroom.google")

SCOPES = [
    "https://www.googleapis.com/auth/classroom.courses.readonly",
    "https://www.googleapis.com/auth/classroom.coursework.students",
    "https://www.googleapis.com/auth/classroom.rosters.readonly",
    "https://www.googleapis.com/auth/classroom.profile.emails",
    "https://www.googleapis.com/auth/drive.readonly",
]
# Google's own formats are exported as PDF
EXPORT_AS_PDF = {
    "application/vnd.google-apps.document",
    "application/vnd.google-apps.presentation",
    "application/vnd.google-apps.spreadsheet",
    "application/vnd.google-apps.drawing",
}
MAX_FILE = 25 * 1024 * 1024


def _paginate(method, key: str, **kw) -> list[dict]:
    out, token = [], None
    while True:
        resp = method(pageToken=token, **kw).execute() if token else method(**kw).execute()
        out.extend(resp.get(key, []))
        token = resp.get("nextPageToken")
        if not token:
            return out


def _files(items) -> list[dict]:
    out = []
    for m in items or []:
        f = m.get("driveFile", {}).get("driveFile") or m.get("driveFile")
        if f and f.get("id"):
            out.append({"file_id": f["id"], "title": f.get("title", ""),
                        "link": f.get("alternateLink", "")})
    return out


class GoogleProvider(Provider):
    mode = "google"

    def __init__(self, token_file: str | None = None, classroom=None, drive=None, access_token: str | None = None):
        self.token_file = token_file or os.environ.get("GOOGLE_TOKEN_FILE", "/secrets/token.json")
        self.access_token = access_token
        self._classroom, self._drive = classroom, drive
        self._rosters: dict[str, dict] = {}

    # -- services
    def _creds(self):
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        if self.access_token:
            return Credentials(token=self.access_token)
        if not os.path.exists(self.token_file):
            raise ProviderError(f"Google token not found at {self.token_file}. "
                                "Run scripts/google_auth.py on your computer first (see README).")
        creds = Credentials.from_authorized_user_file(self.token_file, SCOPES)
        if not creds.valid:
            if creds.expired and creds.refresh_token:
                creds.refresh(Request())
                try:
                    with open(self.token_file, "w") as f:
                        f.write(creds.to_json())
                except OSError:
                    log.warning("could not save refreshed token (read-only mount?)")
            else:
                raise ProviderError("Google token is invalid; run scripts/google_auth.py again")
        return creds

    @property
    def classroom(self):
        if self._classroom is None:
            from googleapiclient.discovery import build
            self._classroom = build("classroom", "v1", credentials=self._creds(), cache_discovery=False)
        return self._classroom

    @property
    def drive(self):
        if self._drive is None:
            from googleapiclient.discovery import build
            self._drive = build("drive", "v3", credentials=self._creds(), cache_discovery=False)
        return self._drive

    # -- API
    def list_courses(self) -> list[dict]:
        cs = _paginate(self.classroom.courses().list, "courses", teacherId="me",
                       courseStates=["ACTIVE"], pageSize=100)
        return [{"id": c["id"], "name": c.get("name", ""), "section": c.get("section", ""),
                 "link": c.get("alternateLink", "")} for c in cs]

    def list_coursework(self, course_id: str) -> list[dict]:
        cw = _paginate(self.classroom.courses().courseWork().list, "courseWork",
                       courseId=course_id, pageSize=100)
        out = []
        for w in cw:
            if w.get("workType", "ASSIGNMENT") != "ASSIGNMENT":
                continue
            due = w.get("dueDate")
            out.append({
                "id": w["id"], "title": w.get("title", ""), "description": w.get("description", ""),
                "max_points": w.get("maxPoints"),
                "due": f"{due['year']:04d}-{due['month']:02d}-{due['day']:02d}" if due else None,
                "materials": _files(w.get("materials")),
                "link": w.get("alternateLink", ""),
            })
        return out

    def _roster(self, course_id: str) -> dict:
        if course_id not in self._rosters:
            st = _paginate(self.classroom.courses().students().list, "students",
                           courseId=course_id, pageSize=100)
            self._rosters[course_id] = {
                s["userId"]: {"id": s["userId"],
                              "name": s.get("profile", {}).get("name", {}).get("fullName", s["userId"]),
                              "email": s.get("profile", {}).get("emailAddress", "")} for s in st}
        return self._rosters[course_id]

    def list_submissions(self, course_id: str, coursework_id: str) -> list[dict]:
        subs = _paginate(self.classroom.courses().courseWork().studentSubmissions().list,
                         "studentSubmissions", courseId=course_id, courseWorkId=coursework_id,
                         pageSize=100)
        roster = self._roster(course_id)
        out = []
        for s in subs:
            uid = s.get("userId")
            stu = roster.get(uid, {"id": uid, "name": uid, "email": ""})
            out.append({
                "id": s["id"], "student": stu, "state": s.get("state", ""),
                "late": bool(s.get("late")),
                "files": _files(s.get("assignmentSubmission", {}).get("attachments")),
                "assigned_grade": s.get("assignedGrade"), "draft_grade": s.get("draftGrade"),
            })
        return out

    def download_file(self, file_id: str) -> dict:
        meta = self.drive.files().get(fileId=file_id, fields="id,name,mimeType,size",
                                      supportsAllDrives=True).execute()
        mime = meta.get("mimeType", "")
        if mime in EXPORT_AS_PDF:
            req = self.drive.files().export_media(fileId=file_id, mimeType="application/pdf")
            mime = "application/pdf"
        elif mime.startswith("application/vnd.google-apps"):
            raise ProviderError(f"cannot download this kind of Google file ({mime.rsplit('.', 1)[-1]})")
        else:
            if int(meta.get("size", 0) or 0) > MAX_FILE:
                raise ProviderError("file too large")
            req = self.drive.files().get_media(fileId=file_id, supportsAllDrives=True)
        return {"file_id": file_id, "title": meta.get("name", ""), "mime": mime,
                "data": self._fetch(req)}

    def _fetch(self, req) -> bytes:
        from googleapiclient.http import MediaIoBaseDownload
        buf = io.BytesIO()
        dl = MediaIoBaseDownload(buf, req)
        done = False
        while not done:
            _, done = dl.next_chunk()
            if buf.tell() > MAX_FILE:
                raise ProviderError("file too large")
        return buf.getvalue()

    def set_grade(self, course_id, coursework_id, submission_id, grade, assign):
        from googleapiclient.errors import HttpError
        body = {"draftGrade": grade}
        mask = "draftGrade"
        if assign:
            body["assignedGrade"] = grade
            mask += ",assignedGrade"
        try:
            self.classroom.courses().courseWork().studentSubmissions().patch(
                courseId=course_id, courseWorkId=coursework_id, id=submission_id,
                updateMask=mask, body=body).execute()
            return {"ok": True}
        except HttpError as e:
            status = getattr(e, "status_code", None) or getattr(getattr(e, "resp", None), "status", None)
            if str(status) == "403":
                return {"ok": False, "error": "Google only lets the app that created an assignment "
                        "set its grades. Use CSV export for assignments made in the Classroom website."}
            return {"ok": False, "error": str(e)}
