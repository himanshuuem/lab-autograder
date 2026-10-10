"""Where code actually runs.

DockerBackend  - production. One throw-away container per program: no network,
                 read-only root, all capabilities dropped, non-root user,
                 memory/CPU/process limits, size-limited tmpfs work dir.
LocalBackend   - development and CI without Docker ONLY. Runs code on the host
                 with no isolation, so it refuses to start unless
                 ALLOW_UNSAFE_LOCAL_BACKEND=1.
"""
from __future__ import annotations

import base64
import contextlib
import os
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass

LABEL = "autograder.sandbox"
CHUNK = 48 * 1024  # bytes per exec when streaming files in (base64 grows by 4/3)


@dataclass
class Limits:
    memory_mb: int = 256
    cpus: float = 1.0
    pids: int = 64
    work_mb: int = 64


@dataclass
class ExecResult:
    exit_code: int
    elapsed_ms: int
    killed: bool = False      # the outer guard had to kill the container


class SandboxError(RuntimeError):
    pass


class Session:
    def write(self, name: str, data: bytes) -> None: ...
    def sh(self, script: str, guard_s: float) -> ExecResult: ...
    def read(self, name: str, limit: int) -> tuple[bytes, bool]: ...


# ---------------------------------------------------------------- docker
class DockerSession(Session):
    def __init__(self, container):
        self.c = container

    def _exec(self, cmd: list[str]) -> tuple[int, bytes]:
        r = self.c.exec_run(cmd, user="10001:10001", workdir="/work", demux=False)
        return r.exit_code, (r.output or b"")

    def write(self, name: str, data: bytes) -> None:
        code, out = self._exec(["sh", "-c", f": > '{name}'"])
        if code != 0:
            raise SandboxError(f"cannot create {name}: {out[:200]!r}")
        for i in range(0, len(data), CHUNK):
            b64 = base64.b64encode(data[i:i + CHUNK]).decode()
            code, out = self._exec(["sh", "-c", f"printf %s '{b64}' | base64 -d >> '{name}'"])
            if code != 0:
                raise SandboxError(f"cannot write {name}: {out[:200]!r}")

    def sh(self, script: str, guard_s: float) -> ExecResult:
        box: dict = {}

        def target():
            try:
                box["r"] = self._exec(["sh", "-c", script])
            except Exception as e:  # container killed underneath us
                box["e"] = e

        t0 = time.monotonic()
        th = threading.Thread(target=target, daemon=True)
        th.start()
        th.join(guard_s)
        elapsed = int((time.monotonic() - t0) * 1000)
        if th.is_alive():  # `timeout` inside failed to stop it: kill everything
            with contextlib.suppress(Exception):
                self.c.kill()
            return ExecResult(137, elapsed, killed=True)
        if "e" in box:
            raise SandboxError(str(box["e"]))
        return ExecResult(box["r"][0], elapsed)

    def read(self, name: str, limit: int) -> tuple[bytes, bool]:
        code, out = self._exec(["sh", "-c", f"head -c {limit + 1} '{name}' 2>/dev/null || true"])
        return out[:limit], len(out) > limit


class DockerBackend:
    name = "docker"

    def __init__(self, client=None):
        if client is None:
            import docker
            client = docker.from_env()
        self.client = client

    def container_kwargs(self, image: str, lim: Limits) -> dict:
        from docker.types import Ulimit
        mem = f"{lim.memory_mb}m"
        return dict(
            image=image,
            command=["sleep", "600"],
            detach=True,
            name=f"grade-{uuid.uuid4().hex[:12]}",
            labels={LABEL: "1"},
            user="10001:10001",
            working_dir="/work",
            network_mode="none",
            read_only=True,
            tmpfs={
                "/work": f"rw,exec,nosuid,nodev,size={lim.work_mb}m,uid=10001,gid=10001,mode=0700",
                "/tmp": "rw,nosuid,nodev,noexec,size=16m,uid=10001,gid=10001,mode=0700",
            },
            mem_limit=mem,
            memswap_limit=mem,          # no swap
            nano_cpus=int(lim.cpus * 1e9),
            pids_limit=lim.pids,
            cap_drop=["ALL"],
            security_opt=["no-new-privileges"],
            ulimits=[Ulimit(name="nofile", soft=256, hard=256),
                     Ulimit(name="core", soft=0, hard=0)],
            ipc_mode="none",
            environment={"HOME": "/work", "LANG": "C.UTF-8", "PYTHONIOENCODING": "utf-8"},
        )

    @contextlib.contextmanager
    def session(self, image: str, lim: Limits):
        c = self.client.containers.run(**self.container_kwargs(image, lim))
        try:
            yield DockerSession(c)
        finally:
            with contextlib.suppress(Exception):
                c.remove(force=True)

    def cleanup_orphans(self) -> int:
        n = 0
        for c in self.client.containers.list(all=True, filters={"label": LABEL}):
            with contextlib.suppress(Exception):
                c.remove(force=True)
                n += 1
        return n

    def image_present(self, image: str) -> bool:
        try:
            self.client.images.get(image)
            return True
        except Exception:
            return False


# ---------------------------------------------------------------- local
class LocalSession(Session):
    def __init__(self, d: str):
        self.d = d

    def write(self, name: str, data: bytes) -> None:
        with open(os.path.join(self.d, name), "wb") as f:
            f.write(data)

    def sh(self, script: str, guard_s: float) -> ExecResult:
        t0 = time.monotonic()
        try:
            p = subprocess.run(["sh", "-c", script], cwd=self.d, timeout=guard_s,
                               capture_output=True, env={"PATH": os.environ.get("PATH", ""),
                                                         "HOME": self.d, "LANG": "C.UTF-8"})
            return ExecResult(p.returncode, int((time.monotonic() - t0) * 1000))
        except subprocess.TimeoutExpired:
            return ExecResult(137, int((time.monotonic() - t0) * 1000), killed=True)

    def read(self, name: str, limit: int) -> tuple[bytes, bool]:
        try:
            with open(os.path.join(self.d, name), "rb") as f:
                data = f.read(limit + 1)
        except FileNotFoundError:
            return b"", False
        return data[:limit], len(data) > limit


class LocalBackend:
    name = "local"

    def __init__(self):
        if os.environ.get("ALLOW_UNSAFE_LOCAL_BACKEND") != "1":
            raise SandboxError("LocalBackend runs untrusted code without isolation; "
                               "set ALLOW_UNSAFE_LOCAL_BACKEND=1 only for development")

    @contextlib.contextmanager
    def session(self, image: str, lim: Limits):
        d = tempfile.mkdtemp(prefix="grade-")
        try:
            yield LocalSession(d)
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def cleanup_orphans(self) -> int:
        return 0

    def image_present(self, image: str) -> bool:
        return True
