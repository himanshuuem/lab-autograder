import pytest
from conftest import have

from sandbox.backends import DockerBackend, LocalBackend, SandboxError
from sandbox.runner import run_program

PY_OK = "n = int(input())\nprint(n * 2)"
C_OK = '#include <stdio.h>\nint main(){int a,b;scanf("%d %d",&a,&b);printf("%d\\n",a+b);return 0;}'
C_MALLOC = ('#include <stdio.h>\n#include <stdlib.h>\nint main(){int n;scanf("%d",&n);'
            'int *a = malloc(n * sizeof(int));for(int i=0;i<n;i++)a[i]=i*i;'
            'printf("%d\\n",a[n-1]);free(a);return 0;}')
CPP_OK = '#include <iostream>\nusing namespace std;\nint main(){string s;cin>>s;cout<<s<<s<<endl;}'
JAVA_OK = ('import java.util.*;\npublic class Twice { public static void main(String[] a){'
           'Scanner s=new Scanner(System.in); System.out.println(s.nextInt()*2);} }')


@pytest.mark.parametrize("lang,src,stdin,out,entry", [
    ("python", PY_OK, "21\n", "42\n", "Main"),
    ("c", C_OK, "3 4\n", "7\n", "Main"),
    ("c", C_MALLOC, "5\n", "16\n", "Main"),     # valid C, invalid C++
    ("cpp", CPP_OK, "ab\n", "abab\n", "Main"),
    pytest.param("java", JAVA_OK, "21\n", "42\n", "Twice",
                 marks=pytest.mark.skipif(not have("javac"), reason="javac not installed")),
])
def test_languages(local_backend, lang, src, stdin, out, entry):
    r = run_program(local_backend, lang, src, [stdin, stdin], entrypoint=entry, time_limit_s=10)
    assert r.compile_status in ("OK", "NOT_NEEDED")
    assert [t.status for t in r.tests] == ["OK", "OK"]
    assert r.tests[0].stdout == out


def test_compile_error(local_backend):
    r = run_program(local_backend, "c", "int main( { return 0; }", ["1"])
    assert r.compile_status == "COMPILE_ERROR" and "error" in r.compile_output and r.tests == []


def test_runtime_error_and_stderr(local_backend):
    r = run_program(local_backend, "python", "print('a')\n1/0", [""])
    t = r.tests[0]
    assert t.status == "RUNTIME_ERROR" and t.stdout == "a\n" and "ZeroDivisionError" in t.stderr


def test_time_limit(local_backend):
    r = run_program(local_backend, "python", "while True: pass", ["", ""], time_limit_s=0.5)
    assert [t.status for t in r.tests] == ["TLE", "TLE"]
    assert all(t.runtime_ms < 5000 for t in r.tests)


def test_output_limit(local_backend):
    r = run_program(local_backend, "python", "while True: print('x' * 1000)", [""], time_limit_s=1)
    assert r.tests[0].status in ("OUTPUT_LIMIT", "TLE")
    assert len(r.tests[0].stdout) <= 64 * 1024


def test_large_stdin_and_unicode(local_backend):
    big = "\n".join(str(i) for i in range(100000)) + "\n"
    r = run_program(local_backend, "python",
                    "import sys\nd=sys.stdin.read().split()\nprint(len(d), 'ঠিক')", [big])
    assert r.tests[0].stdout == "100000 ঠিক\n"


def test_bad_inputs(local_backend):
    with pytest.raises(ValueError):
        run_program(local_backend, "ruby", "", [])
    with pytest.raises(ValueError):
        run_program(local_backend, "java", "", [], entrypoint="../etc/passwd")


def test_local_backend_refuses_without_opt_in(monkeypatch):
    monkeypatch.delenv("ALLOW_UNSAFE_LOCAL_BACKEND")
    with pytest.raises(SandboxError):
        LocalBackend()


# ------------------------------------------------ docker backend (fake client)
def test_container_is_locked_down(fake_docker):
    b = DockerBackend(fake_docker)
    run_program(b, "python", PY_OK, ["2\n"])
    kw = fake_docker.created[0].kwargs
    assert kw["network_mode"] == "none"
    assert kw["read_only"] is True
    assert kw["cap_drop"] == ["ALL"]
    assert "no-new-privileges" in kw["security_opt"]
    assert kw["user"] == "10001:10001"
    assert kw["pids_limit"] == 64
    assert kw["mem_limit"] == kw["memswap_limit"] == "256m"
    assert "size=64m" in kw["tmpfs"]["/work"] and "noexec" in kw["tmpfs"]["/tmp"]
    assert kw["ipc_mode"] == "none"
    assert "volumes" not in kw and "privileged" not in kw
    assert fake_docker.created[0].removed


def test_java_gets_more_memory_and_pids(fake_docker):
    b = DockerBackend(fake_docker)
    run_program(b, "java", JAVA_OK, ["1"], entrypoint="Twice", time_limit_s=10)
    kw = fake_docker.created[0].kwargs
    assert kw["mem_limit"] == "512m" and kw["pids_limit"] == 128


def test_docker_session_streams_files_in_chunks(fake_docker):
    big = "x = 1\n" * 30000  # ~180 KB source -> several base64 chunks
    r = run_program(DockerBackend(fake_docker), "python", big + "print(x)", [""])
    assert r.tests[0].stdout == "1\n"
    writes = [c for c in fake_docker.created[0].execs if "base64 -d" in c[-1]]
    assert len(writes) >= 4


@pytest.mark.skipif(not have("gcc"), reason="gcc")
def test_docker_flow_compiles_and_runs(fake_docker):
    r = run_program(DockerBackend(fake_docker), "c", C_OK, ["1 2", "5 5"])
    assert r.compile_status == "OK" and [t.stdout for t in r.tests] == ["3\n", "10\n"]


def test_container_removed_even_on_error(fake_docker):
    class Boom(Exception):
        pass
    b = DockerBackend(fake_docker)
    orig = fake_docker.containers.run

    def run(**kw):
        c = orig(**kw)
        c.exec_run = lambda *a, **k: (_ for _ in ()).throw(SandboxError("daemon went away"))
        return c
    fake_docker.containers.run = run
    r = run_program(b, "python", PY_OK, ["1"])
    assert r.compile_status == "SANDBOX_ERROR"
    assert fake_docker.created[0].removed


def test_cleanup_orphans_and_images(fake_docker):
    b = DockerBackend(fake_docker)
    fake_docker.containers.run(image="x")
    assert b.cleanup_orphans() == 1
    assert b.image_present("autograder/runner-python") and not b.image_present("missing")


# ------------------------------------------------ Java as OOP students submit it
JAVA_OOP = '''package com.iiest.lab6;

import java.util.Scanner;
import com.iiest.lab6.Shape;

public abstract class Shape {
    public abstract double area();
}

public class Circle extends Shape {
    private final double r;
    public Circle(double r) { this.r = r; }
    @Override
    public double area() { return Math.PI * r * r; }
}

public class Main {
    static class Counter { int n; }

    public static void main(String[] args) {
        Scanner sc = new Scanner(System.in);
        Shape s = new Circle(sc.nextDouble());
        Counter c = new Counter();
        c.n++;
        System.out.printf("%.2f %d%n", s.area(), c.n);
        System.out.println("public class text in a string stays");
    }
}'''


@pytest.mark.skipif(not have("javac"), reason="javac not installed")
def test_java_oop_submission_runs(local_backend):
    r = run_program(local_backend, "java", JAVA_OOP, ["2\n"], entrypoint="Main", time_limit_s=10)
    assert r.compile_status == "OK", r.compile_output
    assert r.tests[0].stdout == "12.57 1\npublic class text in a string stays\n"


def test_prepare_source_java():
    from sandbox.languages import prepare_source
    out = prepare_source("java", JAVA_OOP)
    assert "package" not in out.split("import java.util.Scanner;")[0]
    assert "import com.iiest" not in out
    assert "public class" not in out.replace('"public class text', "")
    assert "abstract class Shape" in out and "public abstract double area()" in out
    assert "public static void main" in out          # methods keep their modifiers
    assert prepare_source("python", "package x;") == "package x;"
