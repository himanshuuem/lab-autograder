"""Compile once, then run every test case, inside one throw-away sandbox."""
from __future__ import annotations

import shlex
from dataclasses import asdict, dataclass, field

from .backends import Limits, SandboxError
from .languages import LANGS, prepare_source, valid_entry

OUTPUT_LIMIT = 64 * 1024
COMPILE_TIMEOUT_S = 30


@dataclass
class TestResult:
    status: str            # OK | RUNTIME_ERROR | TLE | MLE | OUTPUT_LIMIT | SANDBOX_ERROR
    stdout: str
    stderr: str
    exit_code: int | None
    runtime_ms: int
    truncated: bool = False


@dataclass
class RunResult:
    language: str
    compile_status: str    # OK | COMPILE_ERROR | NOT_NEEDED | SANDBOX_ERROR
    compile_output: str = ""
    tests: list[TestResult] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def _dec(b: bytes) -> str:
    return b.decode("utf-8", errors="replace")


def _cmd(argv: list[str]) -> str:
    return " ".join(shlex.quote(a) for a in argv)


def run_program(backend, language: str, source: str, tests: list[str], *,
                entrypoint: str = "Main", time_limit_s: float = 2.0,
                memory_mb: int | None = None, cpus: float = 1.0) -> RunResult:
    if language not in LANGS:
        raise ValueError(f"unsupported language {language!r}")
    if not valid_entry(entrypoint):
        raise ValueError("invalid entrypoint")
    spec = LANGS[language]
    time_limit_s = max(0.1, min(float(time_limit_s), 20.0))
    lim = Limits(memory_mb=min(memory_mb or spec.memory_mb, 2048), cpus=cpus, pids=spec.pids)
    res = RunResult(language=language, compile_status="NOT_NEEDED")
    try:
        with backend.session(spec.image, lim) as s:
            s.write(spec.filename(entrypoint), prepare_source(language, source).encode("utf-8"))
            cc = spec.compile_cmd(entrypoint)
            if cc:
                r = s.sh(f"timeout -s KILL {COMPILE_TIMEOUT_S} {_cmd(cc)} > cc.txt 2>&1",
                         COMPILE_TIMEOUT_S + 15)
                out, _ = s.read("cc.txt", OUTPUT_LIMIT)
                res.compile_output = _dec(out)
                if r.exit_code != 0:
                    res.compile_status = "COMPILE_ERROR"
                    if r.exit_code == 137:
                        res.compile_output += "\n[compiler killed: time or memory limit]"
                    return res
                res.compile_status = "OK"
            run = _cmd(spec.run_cmd(entrypoint))
            for stdin in tests:
                s.write("in.txt", stdin.encode("utf-8"))
                # %.3f-free timeout spec keeps busybox/coreutils both happy
                tl = f"{time_limit_s:g}"
                r = s.sh(f"rm -f out.txt err.txt; timeout -s KILL {tl} {run} < in.txt > out.txt 2> err.txt",
                         time_limit_s + 10)
                out, trunc = s.read("out.txt", OUTPUT_LIMIT)
                err, _ = s.read("err.txt", 8 * 1024)
                if r.killed or (r.exit_code == 137 and r.elapsed_ms >= time_limit_s * 1000 * 0.9):
                    status = "TLE"
                elif r.exit_code == 137:
                    status = "MLE"
                elif trunc:
                    status = "OUTPUT_LIMIT"
                elif r.exit_code != 0:
                    status = "RUNTIME_ERROR"
                else:
                    status = "OK"
                res.tests.append(TestResult(status, _dec(out), _dec(err), r.exit_code,
                                            r.elapsed_ms, trunc))
                if r.killed:  # container is gone; remaining tests can't run
                    for _ in tests[len(res.tests):]:
                        res.tests.append(TestResult("SANDBOX_ERROR", "", "skipped after a hard kill",
                                                    None, 0))
                    break
    except SandboxError as e:
        if res.compile_status == "NOT_NEEDED" and not res.tests:
            res.compile_status = "SANDBOX_ERROR"
            res.compile_output = str(e)
        while len(res.tests) < len(tests) and res.compile_status not in ("COMPILE_ERROR", "SANDBOX_ERROR"):
            res.tests.append(TestResult("SANDBOX_ERROR", "", str(e), None, 0))
    return res
