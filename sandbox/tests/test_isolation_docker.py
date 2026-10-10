"""Real isolation checks. Need a Docker daemon and the runner images:
    make images && make test-docker
"""
import pytest
from conftest import needs_docker

from sandbox.backends import DockerBackend
from sandbox.runner import run_program

pytestmark = [needs_docker, pytest.mark.docker]


@pytest.fixture(scope="module")
def backend():
    return DockerBackend()


def test_no_network(backend):
    src = ("import socket\ntry:\n    socket.create_connection(('8.8.8.8', 53), timeout=2)\n"
           "    print('NET')\nexcept OSError:\n    print('BLOCKED')")
    assert run_program(backend, "python", src, [""]).tests[0].stdout == "BLOCKED\n"


def test_read_only_root(backend):
    src = "try:\n    open('/etc/x','w')\n    print('WROTE')\nexcept OSError:\n    print('RO')"
    assert run_program(backend, "python", src, [""]).tests[0].stdout == "RO\n"


def test_fork_bomb_is_contained(backend):
    src = '#include <unistd.h>\nint main(){while(1) fork();}'
    r = run_program(backend, "c", src, [""], time_limit_s=2)
    assert r.tests[0].status in ("TLE", "RUNTIME_ERROR", "MLE")
    # sandbox still healthy afterwards
    assert run_program(backend, "python", "print(1)", [""]).tests[0].stdout == "1\n"


def test_memory_bomb(backend):
    r = run_program(backend, "python", "a = ' ' * (1 << 30)", [""], time_limit_s=5)
    assert r.tests[0].status in ("MLE", "RUNTIME_ERROR")


def test_runs_as_non_root(backend):
    assert run_program(backend, "python", "import os;print(os.getuid())", [""]).tests[0].stdout == "10001\n"
