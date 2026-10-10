"""Pull questions and sample test cases out of the teacher's assignment PDF.

Understands the usual lab-sheet layout:
    Question 1: Bubble sort
    <statement>
    Sample Input 1:   <block>
    Sample Output 1:  <block>
Anything it gets wrong can be fixed in the dashboard before grading.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from docextract import cleanup
from docextract.indent import by_width
from docextract.pdfread import read_pdf
from docextract.segment import DEFAULT_QUESTION_RE

# "Sample Input 1:", "Input:", "Input - 5 3"; but not the prose "Input a number"
_IN = re.compile(r"^\s*(?:sample|example|test)?\s*(?:case\s*\d*\s*)?input\s*(?:\d+|#\d+)?\s*(?:[:\-]\s*(?P<rest>.*)|$)", re.I)
_OUT = re.compile(r"^\s*(?:sample|example|test|expected)?\s*(?:case\s*\d*\s*)?output\s*(?:\d+|#\d+)?\s*(?:[:\-]\s*(?P<rest>.*)|$)", re.I)
# "1. Create a class Car…": a question numbered without "Q"
_NUMBERED = re.compile(r"^\s*(\d{1,2})\s*[.)]\s*(?P<title>[A-Za-z(].*)$")
# "2.1 Create a class…", "3.1.Create…", "4.11 In an organisation…": numbered within the assignment
_DOTTED = re.compile(r"^\s*(\d{1,2}\.\d{1,2})(?!\d)\s*[.):\-]?\s*(?P<title>.*)$")
_STOP = re.compile(r"^\s*(explanation|constraints?|note|hint|input format|output format)\b", re.I)


@dataclass
class ParsedQuestion:
    label: str
    title: str = ""
    statement: list[str] = field(default_factory=list)
    inputs: list[str] = field(default_factory=list)
    outputs: list[str] = field(default_factory=list)

    @property
    def tests(self) -> list[tuple[str, str]]:
        if not self.outputs:
            return []
        ins = self.inputs + [""] * (len(self.outputs) - len(self.inputs))
        return [(i + ("\n" if i and not i.endswith("\n") else ""), o) for i, o in zip(ins, self.outputs)]


def _is_label(t: str, rx: re.Pattern) -> re.Match | None:
    m = rx.match(t)
    # "Input format: ..." is prose, not a sample block
    if m and not _STOP.match(t) and len(t) < 60:
        return m
    return None


def _numbered_headings(lines, qre) -> dict[int, tuple[str, str]]:
    """When a sheet has no "Q1"/"Question 1" headings, a list 1., 2., 3.… starting at the
    left margin numbers the questions. Indented or out-of-sequence numbers (a sub-list
    inside a question) don't count. Returns {id(line): (label, title)}."""
    real = [ln for ln in lines if (m := qre.match(ln.text.strip()))
            and not ln.text.strip().lower().startswith("assign")]
    if len(real) >= 2:
        return {}
    dotted = _dotted_headings(lines)
    if len(dotted) >= 2:
        return dotted
    cands = [(ln, m) for ln in lines if (m := _NUMBERED.match(ln.text)) and not ln.mono]
    if not cands:
        return {}
    margin = min(ln.x for ln, _ in cands)
    found, want = {}, 1
    for ln, m in cands:
        if int(m.group(1)) == want and ln.x <= margin + 6:
            found[id(ln)] = (m.group(1), m.group("title").strip(" :.-"))
            want += 1
    return found if len(found) >= 2 else {}


def _dotted_headings(lines) -> dict[int, tuple[str, str]]:
    """2.1, 2.2, 2.3…: same first number, in increasing order."""
    cands = [(ln, m) for ln in lines if (m := _DOTTED.match(ln.text)) and not ln.mono]
    if not cands:
        return {}
    found, last = {}, 0
    major = None
    for ln, m in cands:
        mj, mn = (int(x) for x in m.group(1).split("."))
        if mn <= last or (major is not None and mj != major):
            continue
        found[id(ln)] = (m.group(1), m.group("title").strip(" :.-"))
        major, last = mj, mn
    return found if len(found) >= 2 else {}


def parse_assignment_pdf(path: str) -> list[ParsedQuestion]:
    rd = read_pdf(path)
    from collections import Counter
    rep = Counter()
    lines = cleanup.remove_headers_footers(cleanup.normalize_lines(rd.lines, rep), rep)
    qre = re.compile(DEFAULT_QUESTION_RE, re.I)
    numbered = _numbered_headings(lines, qre)
    qs: list[ParsedQuestion] = []
    cur: ParsedQuestion | None = None
    mode, block, inline = None, [], None

    def flush():
        nonlocal block, mode, inline
        if cur is not None and mode in ("in", "out"):
            text = "\n".join(filter(None, [inline, by_width(block) if block else ""])).strip("\n")
            (cur.inputs if mode == "in" else cur.outputs).append(text)
        block, mode, inline = [], None, None

    for ln in lines:
        t = ln.text.strip()
        if numbered:
            if id(ln) in numbered:
                flush()
                label, title = numbered[id(ln)]
                cur = ParsedQuestion(label=label, title=title)
                qs.append(cur)
                continue
        elif (m := qre.match(t)):
            flush()
            cur = ParsedQuestion(label=m.group(1), title=t[m.end():].strip(" :.-") or t)
            qs.append(cur)
            continue
        if cur is None:
            continue
        mi, mo = _is_label(t, _IN), _is_label(t, _OUT)
        if mi and not t.lower().startswith(("output", "sample output", "expected")):
            flush(); mode = "in"; inline = (mi.group("rest") or "").strip() or None
            continue
        if mo:
            flush(); mode = "out"; inline = (mo.group("rest") or "").strip() or None
            continue
        if _STOP.match(t):
            flush(); mode = "skip"
            continue
        if mode in ("in", "out"):
            # sample blocks are usually monospace; a prose line ends the block
            if block and not ln.mono and any(b.mono for b in block):
                flush()
                cur.statement.append(t)
            else:
                block.append(ln)
        elif mode != "skip":
            cur.statement.append(t)
    flush()
    # "Assignment- 4- 2nd Part" above "Assignment 4.4", "Assignment 4.5": the title, not a question
    majors = {q.label.split(".")[0] for q in qs if "." in q.label}
    return [q for q in qs if not (q.label in majors and not q.tests)]
