import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "app"), str(ROOT / "packages" / "docextract"),
                str(ROOT / "mcp_server"), str(ROOT / "sandbox")]
os.environ["AUTOGRADER_NO_APP"] = "1"
os.environ["ALLOW_UNSAFE_LOCAL_BACKEND"] = "1"

import shutil

import pytest

from classroom_mcp.demo_provider import DemoProvider
from classroom_mcp.provider import ProviderError

HAVE_JAVAC = shutil.which("javac") is not None


class FakeClassroom:
    """Same interface as ClassroomClient, backed by the demo provider in-process."""
    provider = None

    def __init__(self, *a, **k):
        if FakeClassroom.provider is None:
            FakeClassroom.provider = DemoProvider()
        self.p = FakeClassroom.provider
        self.fail_grades = False

    def _wrap(self, fn, *a):
        from autograder.clients import ServiceError
        try:
            return fn(*a)
        except ProviderError as e:
            raise ServiceError(str(e))

    def courses(self): return self._wrap(self.p.list_courses)
    def coursework(self, c): return self._wrap(self.p.list_coursework, c)
    def submissions(self, c, w): return self._wrap(self.p.list_submissions, c, w)

    def download(self, fid):
        f = self._wrap(self.p.download_file, fid)
        return f["title"], f["data"]

    def set_grade(self, c, w, s, g, assign=False):
        if FakeClassroom.fail_grades_403:
            return {"ok": False, "error": "Google only lets the app ... Use CSV export ..."}
        return self.p.set_grade(c, w, s, g, assign)

    def info(self): return {"mode": "demo"}


FakeClassroom.fail_grades_403 = False


class LocalSandbox:
    """Same interface as SandboxClient, running the real sandbox runner locally."""
    def __init__(self, *a, **k):
        from sandbox.backends import LocalBackend
        self.b = LocalBackend()

    def run(self, language, source, tests, *, entrypoint="Main", time_limit_s=2.0):
        from sandbox.runner import run_program
        return run_program(self.b, language, source, tests, entrypoint=entrypoint,
                           time_limit_s=time_limit_s).to_dict()

    def health(self):
        return {"ok": True, "backend": "local", "images": {}}


def fresh_db_url(tmp_path) -> str:
    """SQLite by default; set TEST_DATABASE_URL to run against PostgreSQL (tables are reset)."""
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        return f"sqlite:///{tmp_path}/t.db"
    from sqlalchemy import create_engine
    from autograder import models  # noqa: F401
    from autograder.db import Base
    eng = create_engine(url)
    Base.metadata.drop_all(eng)
    eng.dispose()
    return url


@pytest.fixture
def app_env(tmp_path, monkeypatch):
    from autograder import config
    monkeypatch.setattr(config.settings, "database_url", fresh_db_url(tmp_path))
    monkeypatch.setattr(config.settings, "data_dir", str(tmp_path / "data"))
    monkeypatch.setattr(config.settings, "admin_password", "pw")
    monkeypatch.setattr(config.settings, "grading_workers", 3)
    FakeClassroom.provider = None
    FakeClassroom.fail_grades_403 = False
    from autograder import api
    monkeypatch.setattr(api, "classroom_client", FakeClassroom)
    monkeypatch.setattr(api, "sandbox_client", LocalSandbox)
    return tmp_path
