import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

needs_tesseract = pytest.mark.skipif(shutil.which("tesseract") is None, reason="tesseract not installed")


def run_program(code: str, language: str, stdin: str = "", entry: str | None = None) -> str:
    """Compile and run OUR OWN sample programs (test fixtures only) and return stdout."""
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        if language == "python":
            (d / "main.py").write_text(code)
            cmd = [sys.executable, str(d / "main.py")]
        elif language in ("c", "cpp"):
            src = d / ("main.c" if language == "c" else "main.cpp")
            src.write_text(code)
            cc = "gcc" if language == "c" else "g++"
            subprocess.run([cc, str(src), "-o", str(d / "a.out")], check=True, capture_output=True)
            cmd = [str(d / "a.out")]
        elif language == "java":
            f = d / f"{entry}.java"
            f.write_text(code)
            cmd = ["java", str(f)]
        else:
            raise ValueError(language)
        r = subprocess.run(cmd, input=stdin, capture_output=True, text=True, timeout=60)
        assert r.returncode == 0, r.stderr
        return r.stdout


@pytest.fixture
def tmp(tmp_path):
    return tmp_path
