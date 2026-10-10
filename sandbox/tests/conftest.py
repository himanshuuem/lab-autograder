import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
os.environ.setdefault("ALLOW_UNSAFE_LOCAL_BACKEND", "1")


class FakeContainer:
    """Executes exec_run commands in a temp dir, like a container would."""
    def __init__(self, kwargs):
        self.kwargs = kwargs
        self.dir = tempfile.mkdtemp()
        self.removed = False
        self.killed = False
        self.execs = []

    def exec_run(self, cmd, user=None, workdir=None, demux=False):
        self.execs.append(cmd)
        p = subprocess.run(cmd, cwd=self.dir, capture_output=True, timeout=60)
        return SimpleNamespace(exit_code=p.returncode, output=p.stdout + p.stderr)

    def kill(self):
        self.killed = True

    def remove(self, force=False):
        self.removed = True
        shutil.rmtree(self.dir, ignore_errors=True)


class FakeDockerClient:
    def __init__(self):
        self.created = []
        outer = self

        class Containers:
            def run(self, **kw):
                c = FakeContainer(kw)
                outer.created.append(c)
                return c

            def list(self, all=False, filters=None):
                return [c for c in outer.created if not c.removed]

        class Images:
            def get(self, name):
                if "missing" in name:
                    raise LookupError(name)
                return object()

        self.containers = Containers()
        self.images = Images()


@pytest.fixture
def fake_docker():
    return FakeDockerClient()


@pytest.fixture
def local_backend():
    from sandbox.backends import LocalBackend
    return LocalBackend()


def have(cmd):
    return shutil.which(cmd) is not None


def _docker_ok():
    try:
        import docker
        docker.from_env().ping()
        return True
    except Exception:
        return False


needs_docker = pytest.mark.skipif(not _docker_ok(), reason="needs a working Docker daemon")
