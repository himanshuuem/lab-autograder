"""Guess the language of an extracted program: python, java, cpp or c."""
from __future__ import annotations

import re

_RULES = {
    "python": [
        (r"^\s*def \w+\s*\(", 4), (r"^\s*(import \w+|from \w+(\.\w+)* import )", 3),
        (r"\bprint\(", 2), (r"^\s*(if|elif|while|for) .*:\s*$", 2), (r"\binput\(", 2),
        (r"\bself\b", 2), (r"\brange\(", 2), (r"\belif\b", 4), (r"\bTrue\b|\bFalse\b|\bNone\b", 1),
        (r"^\s*#(?!include|define|pragma)", 1), (r"\blen\(", 1),
    ],
    "java": [
        (r"\bpublic\s+static\s+void\s+main\b", 6), (r"\bSystem\.(out|in)\b", 5),
        (r"^\s*import java\.", 5), (r"\bpublic\s+class\b", 3), (r"\bnew Scanner\b", 4),
        (r"\bString\[\]", 3), (r"\bextends\b|\bimplements\b", 2),
    ],
    "cpp": [
        (r"#include\s*<(iostream|bits/stdc\+\+\.h|vector|string|algorithm|map|set|queue|stack|cmath|fstream|sstream|unordered_map)>", 6),
        (r"\b(std::|cout|cin|endl)\b", 4), (r"\busing namespace std\b", 5),
        (r"\b(vector|string)<", 2), (r"\bclass \w+\s*\{", 1), (r"\btemplate\s*<", 3),
        (r"\bnew \w+|\bdelete\b", 1),
    ],
    "c": [
        (r"#include\s*<(stdio|stdlib|string|math|ctype|limits|stdbool)\.h>", 5),
        (r"\b(printf|scanf)\s*\(", 3), (r"\bmalloc\s*\(|\bfree\s*\(", 2),
        (r"\bstruct \w+", 1), (r"\btypedef\b", 1),
    ],
}
_COMPILED = {k: [(re.compile(p, re.M), w) for p, w in v] for k, v in _RULES.items()}


def detect_language(code: str) -> tuple[str | None, dict[str, int]]:
    scores = {lang: sum(w for rx, w in rules if rx.search(code))
              for lang, rules in _COMPILED.items()}
    # C headers inside a C++ program (e.g. <stdio.h> + cout) -> C++
    if scores["cpp"] >= 4 and scores["c"]:
        scores["c"] = 0
    # braces/semicolons are strong evidence against Python
    if code.count(";") >= 3 and code.count("{") >= 1:
        scores["python"] = max(0, scores["python"] - 4)
    best = max(scores, key=scores.get)
    return (best if scores[best] >= 3 else None), scores


_JAVA_PUBLIC = re.compile(r"\bpublic\s+(?:final\s+|abstract\s+)*class\s+([A-Za-z_]\w*)")
_JAVA_ANY_CLASS = re.compile(r"\bclass\s+([A-Za-z_]\w*)")
_JAVA_SCAN = re.compile(r"\b(?:class|interface|enum|record)\s+([A-Za-z_]\w*)|\bstatic\s+void\s+main\s*\(|[{}]")
_JAVA_NOISE = re.compile(r'//[^\n]*|/\*[\s\S]*?\*/|"(?:\\.|[^"\\\n])*"|\'(?:\\.|[^\'\\\n])*\'')


def java_main_class(code: str) -> str | None:
    """The class whose body contains `static void main`, found by tracking braces
    (so a nested class declared before main doesn't confuse it)."""
    clean = _JAVA_NOISE.sub(lambda m: " " * len(m.group(0)), code)
    stack: list[tuple[str, int]] = []
    pending, depth = None, 0
    for m in _JAVA_SCAN.finditer(clean):
        tok = m.group(0)
        if m.group(1):
            pending = m.group(1)
        elif tok == "{":
            depth += 1
            if pending:
                stack.append((pending, depth))
                pending = None
        elif tok == "}":
            if stack and stack[-1][1] == depth:
                stack.pop()
            depth -= 1
        else:  # main
            return stack[0][0] if stack else None
    return None


def java_entrypoint(code: str) -> str | None:
    """Class to run: the one with main, else the public class, else the first class.
    (The sandbox removes `public` from top-level classes, so the file name is free.)"""
    name = java_main_class(code)
    if name:
        return name
    m = _JAVA_PUBLIC.search(code) or _JAVA_ANY_CLASS.search(code)
    return m.group(1) if m else None
