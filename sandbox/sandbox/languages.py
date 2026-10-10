"""How each language is compiled and run inside its runner image."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass

_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")


@dataclass(frozen=True)
class Lang:
    name: str
    image: str
    source: str                 # file name; {entry} is replaced for Java
    compile: tuple[str, ...] | None
    run: tuple[str, ...]
    memory_mb: int = 256
    pids: int = 64

    def filename(self, entry: str) -> str:
        return self.source.format(entry=entry)

    def compile_cmd(self, entry: str) -> list[str] | None:
        return [p.format(entry=entry) for p in self.compile] if self.compile else None

    def run_cmd(self, entry: str) -> list[str]:
        return [p.format(entry=entry) for p in self.run]


def _img(lang: str, default: str) -> str:
    return os.environ.get(f"RUNNER_IMAGE_{lang.upper()}", default)


LANGS: dict[str, Lang] = {
    "python": Lang("python", _img("python", "autograder/runner-python:latest"), "main.py",
                   None, ("python3", "-I", "-B", "main.py")),
    "c": Lang("c", _img("c", "autograder/runner-gcc:latest"), "main.c",
              ("gcc", "-O2", "-std=gnu11", "-o", "prog", "main.c", "-lm"), ("./prog",)),
    "cpp": Lang("cpp", _img("cpp", "autograder/runner-gcc:latest"), "main.cpp",
                ("g++", "-O2", "-std=gnu++17", "-o", "prog", "main.cpp"), ("./prog",)),
    "java": Lang("java", _img("java", "autograder/runner-java:latest"), "{entry}.java",
                 ("javac", "-J-Xmx256m", "-J-XX:-UsePerfData", "-encoding", "UTF-8", "{entry}.java"),
                 ("java", "-Xmx192m", "-Xss32m", "-XX:+UseSerialGC", "-XX:-UsePerfData",
                  "-XX:TieredStopAtLevel=1", "-cp", ".", "{entry}"),
                 memory_mb=512, pids=128),
}


def valid_entry(entry: str) -> bool:
    return bool(_IDENT.match(entry))


# ---------------------------------------------------------------- source fixes
# Students paste several files into one PDF. Java needs one public class per file
# named after it, and IDEs add `package` lines; neither works for a single file run
# with `java ClassName`. Removing them changes nothing about what the program does.
_PKG = re.compile(r"^[ \t]*package[ \t]+([\w.]+)[ \t]*;[ \t]*$", re.M)
_PUBLIC_TYPE = re.compile(
    r"^([ \t]*)public[ \t]+(?=(?:(?:abstract|final|static|sealed|non-sealed|strictfp)[ \t]+)*"
    r"(?:class|interface|enum|record)\b)", re.M)


def prepare_source(language: str, source: str) -> str:
    if language != "java":
        return source
    pkgs = _PKG.findall(source)
    source = _PKG.sub("", source)
    for pkg in set(pkgs):  # imports of the student's own package now point nowhere
        source = re.sub(rf"^[ \t]*import[ \t]+(?:static[ \t]+)?{re.escape(pkg)}\.[\w.*]+[ \t]*;[ \t]*$",
                        "", source, flags=re.M)
    return _PUBLIC_TYPE.sub(r"\1", source)
