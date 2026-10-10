"""Deterministic output comparison. No LLM decides a grade."""
from __future__ import annotations

import difflib
import math
import re

MODES = ("tokens", "lines", "exact")
_NUM = re.compile(r"^[-+]?(\d+\.?\d*|\.\d+)([eE][-+]?\d+)?$")


def normalize(s: str | None) -> str:
    s = (s or "").replace("\r\n", "\n").replace("\r", "\n")
    lines = [ln.rstrip() for ln in s.split("\n")]
    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines)


def tokens(s: str | None) -> list[str]:
    return (s or "").split()


def _tok_eq(a: str, b: str, tol: float) -> bool:
    if a == b:
        return True
    if _NUM.match(a) and _NUM.match(b):
        x, y = float(a), float(b)
        return math.isclose(x, y, rel_tol=tol, abs_tol=tol)
    return False


def outputs_match(actual: str, expected: str, mode: str = "tokens", tol: float = 1e-6) -> bool:
    if mode == "exact":
        return normalize(actual) == normalize(expected)
    if mode == "lines":
        a = [" ".join(l.split()) for l in normalize(actual).split("\n")]
        e = [" ".join(l.split()) for l in normalize(expected).split("\n")]
        return a == e
    a, e = tokens(actual), tokens(expected)
    return len(a) == len(e) and all(_tok_eq(x, y, tol) for x, y in zip(a, e))


def _contains(hay: list[str], needle: list[str], tol: float = 1e-6) -> bool:
    """needle appears in hay as a contiguous run, or (if long enough) as a
    subsequence: terminal copies interleave the typed input with the output."""
    if not needle:
        return False
    n = len(needle)
    for i in range(len(hay) - n + 1):
        if all(_tok_eq(hay[i + k], needle[k], tol) for k in range(n)):
            return True
    if n >= 3:
        it = iter(hay)
        return all(any(_tok_eq(h, t, tol) for h in it) for t in needle)
    return False


def _squash(s: str | None) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip().lower()


def _coverage(needle: str, hay: str) -> float:
    """How much of `needle` appears, in order, inside `hay` (0..1). Tolerates OCR
    slips (1/l, 0/O, a lost space) and extra text such as echoed input."""
    if not needle:
        return 0.0
    sm = difflib.SequenceMatcher(None, needle, hay, autojunk=False)
    return sum(b.size for b in sm.get_matching_blocks()) / len(needle)


def _fuzzy_contains(hay: str, needle: str) -> bool:
    """Words may be slightly misread, numbers may not: the digits of `needle`
    must appear unbroken in `hay` (spaces between them may be lost by OCR)."""
    n, h = _squash(needle), _squash(hay)
    if not n:
        return False
    if len(n) < 6:   # short answers must match as whole tokens
        return _contains(h.split(), n.split())
    dn, dh = re.sub(r"\D", "", n), re.sub(r"\D", "", h)
    if dn and dn not in dh:
        return False
    # OCR often drops the space between single digits ("1 2 3" -> "123"), so
    # compare without whitespace; the digit check above keeps numbers exact
    return _coverage(n.replace(" ", ""), h.replace(" ", "")) >= 0.85


def claimed_status(claimed: str | None, runs: list[tuple[str, str]], fuzzy: bool = False) -> str:
    """runs: (actual stdout, expected) per test.
    NONE                   no output in the PDF
    MATCHES_ACTUAL         the PDF output is what the program really prints
    MATCHES_EXPECTED_ONLY  the PDF shows the right answer, the program doesn't print it
    NO_MATCH               neither (probably run with other input)"""
    if not claimed or not claimed.strip():
        return "NONE"
    if fuzzy:   # read from a screenshot by OCR
        if any(_fuzzy_contains(claimed, a) for a, _ in runs):
            return "MATCHES_ACTUAL"
        if any(_fuzzy_contains(claimed, e) and not _fuzzy_contains(e, a) for a, e in runs):
            return "MATCHES_EXPECTED_ONLY"
        return "NO_MATCH"
    c = tokens(claimed)
    if any(_contains(c, tokens(a)) for a, _ in runs):
        return "MATCHES_ACTUAL"
    if any(_contains(c, tokens(e)) for _, e in runs):
        return "MATCHES_EXPECTED_ONLY"
    return "NO_MATCH"
