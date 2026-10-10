"""Split a submission into questions, and each question into code + claimed output."""
from __future__ import annotations

import re
from dataclasses import dataclass, field, replace

from .pdfread import Line

# "Q4.5" and "Assignment 2.3" keep the whole number: sheets number questions 2.1, 2.2…
DEFAULT_QUESTION_RE = (
    r"^\s*(?:Q|Qn|Qs|Ques|Quest|Question|Problem|Prob|Program|Prog|Experiment|Expt|Exp|"
    r"Task|Assignment|Exercise|Ex)\s*(?:No\.?|Number)?\s*[-.:#_]?\s*(\d{1,3}(?:\.\d{1,2}(?!\d))?)\s*(?:[).:\-]|\b)"
)
_CODE_MARK = re.compile(r"^\s*(source\s*code|code|program(\s*code)?|solution|implementation|answer|ans)\s*[:\-]{0,2}\s*$", re.I)
# "Code :- class" with the rest of the line in the next one (a justified paragraph): the marker,
# then code that starts on the same line
_CODE_MARK_INLINE = re.compile(r"^\s*(?:source\s*code|code|program\s*code)\s*:-?\s*(?P<rest>(?:(?:public|abstract|final)\s+)*"
                               r"(?:class|interface|import|package)\b.*)$", re.I)
# "Output:" (anything may follow the colon) or a bare "Output" / "Sample Output -" line.
_OUTPUT_MARK = re.compile(
    r"^\s*(?:(?:sample|program|expected|my|actual)\s+)?(?:outputs?|o\s*/\s*p|op|screen\s*shot)\s*(?:\(s\))?\s*(?::\s*(?P<rest>.*)|-?\s*)$", re.I)
# "// OUTPUT.." or "# Output: 5" typed as a comment under the code. Only all-caps OUTPUT or
# output followed by a colon or dots counts, so an ordinary "# output the total" comment doesn't.
_OUTPUT_COMMENT = re.compile(
    r"^\s*(?://+|#+|/\*+)\s*(?:(?:[Ss]ample|SAMPLE|[Pp]rogram|PROGRAM|[Mm]y|MY)\s+)?"
    r"(?:OUTPUTS?\b|[Oo]utputs?(?=\s*(?::|\.\.)))\s*[:.\-=]*\s*(?P<rest>.*?)\s*(?:\*+/)?$")
_INPUT_MARK = re.compile(
    r"^\s*(?:(?:sample|test)\s+)?inputs?\s*(?:\(s\))?\s*(?::.*|-?\s*)$", re.I)

# `output: int = 5` is Python code, not an "Output:" label
_ANNOTATION = re.compile(
    r"^\s*\w+\s*:\s*(?:int|float|str|bool|list|dict|set|tuple|bytes|complex|"
    r"List|Dict|Set|Tuple|Optional|Any)\b[\w\[\], .]*=(?!=)")

_CODE_START = re.compile(
    r"^(#include|#define|import |from \S+ import|using namespace|package |public |private |"
    r"protected |static |abstract |final |interface |enum |@Override\b|@FunctionalInterface\b|"
    r"class |struct |typedef |def |return\b|int |long |float |double |char |"
    r"void |bool |string |auto |const |for\s*\(|for \w+ in |while\s*[\(\w]|if\s*\(|if \w|else\b|"
    r"elif |try\s*[:{]|except\b|catch\s*\(|switch\s*\(|case .*:|break;|continue;|print\(|"
    r"printf\(|scanf\(|cout\b|cin\b|System\.|Scanner |std::|vector<|try:|with |"
    # the same, auto-capitalised by Word (fixed later in cleanup)
    r"Print\(|Printf\(|Scanf\(|Def \w+\(|Return\b|Int main|Cout\b|Cin\b)")
_COMMENT = re.compile(r"^(//|/\*|\*/|\*\s|#(?!\s*\d)|\"\"\"|''')")


@dataclass
class Section:
    label: str
    statement: list[Line] = field(default_factory=list)
    code: list[Line] = field(default_factory=list)
    output: list[Line] = field(default_factory=list)
    output_inline: list[str] = field(default_factory=list)
    had_code_marker: bool = False
    had_output_marker: bool = False
    code_blocks: int = 0
    heading_word: str | None = None    # "Q", "Question", "Assignment"… when a heading started it
    guessed: bool = False               # numbered by position (a document with no headings)


# "Part_2 :", "Q.1)", "Answer -", "Ques 3:" alone on a line: labels, whatever font they're in
_LABEL_LINE = re.compile(r"^(?:part|answer|ans|solution|question|ques|qn|q)[\s_.\-#]*\d{0,3}(?:\.\d{1,2})?[a-z]?\s*[:.)\-]*\s*$", re.I)


def label_key(label: str) -> tuple:
    """Order question labels as numbers: 2 < 4.4 < 4.10 < 10; anything else last."""
    m = re.fullmatch(r"(\d+)(?:\.(\d+))?", label or "")
    return (int(m.group(1)), int(m.group(2) or 0)) if m else (10**6, 0)


def code_score(ln: Line) -> int:
    t = ln.text.strip()
    if _LABEL_LINE.match(t):
        return -5
    s = 2 if ln.mono else 0
    if t in ("{", "}", "};", "});", ")", "]"):
        return s + 4
    if _CODE_START.match(t):
        s += 3
    if _COMMENT.match(t):
        s += 2
    if re.search(r"[;{}]\s*(//.*)?$", t):
        s += 3
    if re.search(r"\w\s*(==|!=|<=|>=|\+=|-=|\*=|/=|%=|<<|>>|\+\+|--|=)\s*\S", t):
        s += 1
    if re.search(r"\w\([^)]*\)", t):
        s += 1
    if re.match(r"(def|if|elif|else|for|while|try|except|finally|class|with)\b.*:$", t):
        s += 3
    words = re.findall(r"[A-Za-z]{2,}", t)
    # a statement split over lines: `Account a =`, `new SavingsAccount(`, `"S101", 20000,`
    if t.endswith(("=", "(", ",", "+", "&&", "||", "->")) and len(words) <= 5 and not t.endswith(("==", "+=")):
        s += 2
    if len(words) >= 7 and t.endswith((".", "?")) and not t.endswith(");"):
        s -= 4
    elif len(words) >= 6 and not re.search(r"[;{}()=\[\]<>]", t):
        s -= 3
    return s


def _pick_code(cands: list[Line], marked: bool) -> tuple[list[Line], int]:
    if not cands:
        return [], 0
    thr = 1 if marked else 2
    scores = [code_score(ln) for ln in cands]
    is_code = [s >= thr for s in scores]
    # bridge short gaps of neutral (non-prose) lines between code lines
    idx = [i for i, c in enumerate(is_code) if c]
    for a, b in zip(idx, idx[1:]):
        if 1 < b - a <= 3 and all(scores[j] >= 0 for j in range(a + 1, b)):
            for j in range(a + 1, b):
                is_code[j] = True
    # keep an indented line that ends a block (e.g. a final `print(x)` typed in
    # a proportional font scores low on its own)
    for i in range(1, len(cands)):
        if not is_code[i] and is_code[i - 1] and scores[i] >= 1 and not cands[i].image:
            block_x = min(c.x for c, k in zip(cands[:i], is_code[:i]) if k)
            if cands[i].x > block_x + 1:
                is_code[i] = True
    runs, cur = [], []
    for ln, c in zip(cands, is_code):
        if c:
            cur.append(ln)
        elif cur:
            runs.append(cur); cur = []
    if cur:
        runs.append(cur)
    min_len = 1 if marked else 2
    runs = [r for r in runs if len(r) >= min_len]
    return [ln for r in runs for ln in r], len(runs)


def _image_runs(lines: list[Line]) -> list[tuple[int, int]]:
    """(start, end) index ranges of consecutive lines read from one screenshot."""
    runs, i = [], 0
    while i < len(lines):
        if lines[i].image:
            j = i
            while j + 1 < len(lines) and lines[j + 1].image and lines[j + 1].page == lines[i].page \
                    and lines[j + 1].y - lines[j].y < 60:
                j += 1
            runs.append((i, j + 1))
            i = j + 1
        else:
            i += 1
    return runs


def _split_screenshots(sec: Section) -> None:
    """A screenshot is judged as a whole: mostly code means a code screenshot,
    anything else (program output, terminal) becomes the claimed output."""
    for attr in ("statement", "code"):
        bucket = getattr(sec, attr)
        keep, moved = [], []
        runs = _image_runs(bucket)
        out_idx = set()
        for a, b in runs:
            run = bucket[a:b]
            codey = sum(code_score(ln) >= 2 for ln in run)
            if codey < 0.5 * len(run):
                out_idx.update(range(a, b))
        for i, ln in enumerate(bucket):
            (moved if i in out_idx else keep).append(ln)
        if moved:
            setattr(sec, attr, keep)
            sec.output = sorted(sec.output + moved, key=lambda l: (l.page, l.y))
            sec.had_output_marker = True


# "1. Create a class Car", "2)", "3:" or "4 -" starting a line: a question numbered without "Q"
_NUM_HEAD = re.compile(r"^\s*(\d{1,2})\s*[.):\-]\s*(?P<rest>.*)$")
# where a new program starts in a document with no headings
_PROGRAM_START = re.compile(r"^\s*(?:import\s|package\s|#\s*include|(?:(?:public|final|abstract)\s+)*"
                            r"(?:class|interface|enum)\s+\w)")
_COMMENT_HEAD = re.compile(r"^\s*(?://+|#+|/\*+)\s*(?P<body>.*?)\s*(?:\*+/)?\s*$")
_STRINGS = re.compile(r'"(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)\'')


def _rest_line(ln: Line, rest: str) -> Line:
    """The code after an inline heading ("Q1- class Car {"), placed where the line starts."""
    return replace(ln, text=rest)


def _find_headings(lines: list[Line], qre: re.Pattern) -> dict[int, tuple[str, str | None, Line | None]]:
    """{id(line): (label, heading word, code on the same line)} for every question heading."""
    hits: dict[int, tuple[str, str | None, Line | None]] = {}
    real = 0
    for ln in lines:
        t = ln.text.strip()
        m = qre.match(t)
        commented = None
        if not m and (cm := _COMMENT_HEAD.match(t)):
            commented = cm.group("body")            # "// Question 1", "# Q2", "/* Q3 */"
            m = qre.match(commented)
            if m:
                rest = commented[m.end():].strip()
                # "// Question 1 --", "// Q1: Bubble sort", "# Question 3" are headings;
                # "// Question 2 is below" and "// q1 = q2 + 1;" are ordinary comments
                titled = commented[:m.end()].rstrip()[-1:] in "-:.)\u2014"
                if (rest.strip(" -\u2014:.)*/") and not titled) or \
                        code_score(replace(ln, text=rest, mono=False)) >= 2:
                    m = None
        if not m:
            continue
        if commented is not None:
            hits[id(ln)] = (m.group(1), re.match(r"\s*([A-Za-z]*)", commented).group(1) or None, None, True)
            real += 1
            continue
        word = re.match(r"\s*([A-Za-z]*)", t).group(1) or None
        rest = t[m.end():].strip()
        if not t.endswith((";", "{")) and code_score(ln) < 3:
            hits[id(ln)] = (m.group(1), word, None)
        elif t[:m.end()].rstrip()[-1:] in "-:.)" and rest and code_score(_rest_line(ln, rest)) >= 3:
            hits[id(ln)] = (m.group(1), word, _rest_line(ln, rest))      # "Q1- class Car {"
        else:
            continue
        real += not (word or "").lower().startswith("assign")
    if real >= 2:
        return hits
    dotted = _dotted_headings(lines)
    if len(dotted) >= 2:
        return dotted
    chain = _numbered_chain(lines, qre, hits)
    if len(chain) >= 2:
        return chain
    return hits if real else {}


# "4.5", "2.3)" or "4.11. Create a class…" starting a line: a sheet's own question number
_DOTTED_HEAD = re.compile(r"^\s*(\d{1,2}\.\d{1,2})(?!\d)\s*[.):\-]?\s*(?P<rest>.*)$")


def _dotted_headings(lines: list[Line]) -> dict:
    """Answers headed by the sheet's numbers without a "Q": 4.4, 4.5, 4.6… Each must be a
    different number, outside code (`2.5 * r` or `double x = 4.5;` are never headings), all
    with the same first number and in increasing order (a printed 78.5 is not a heading)."""
    cands = []
    for ln in lines:
        m = _DOTTED_HEAD.match(ln.text)
        if not m or ln.image:
            continue
        rest = m.group("rest").strip()
        if rest[:1] in ("*", "+", "/", "-", "=", ";", ",", ")", "%") or ln.text.rstrip().endswith((";", "{", ",")) \
                or re.match(r"[fFdDlL]\b", rest):
            continue
        major, minor = (int(x) for x in m.group(1).split("."))
        if 1 <= major <= 12 and 1 <= minor <= 15:
            cands.append((ln, major, minor, m.group(1)))
    if not cands:
        return {}
    from collections import Counter
    major = Counter(c[1] for c in cands).most_common(1)[0][0]
    hits, last = {}, 0
    for ln, mj, mn, label in cands:
        if mj == major and mn > last:
            hits[id(ln)] = (label, "Q", None)
            last = mn
    return hits


def _numbered_chain(lines: list[Line], qre: re.Pattern, qhits: dict) -> dict:
    """Questions numbered 1., 2), 3: at the left margin, in order and a few lines apart.
    Numbers on consecutive lines are code line numbers or a numbered menu, never headings."""
    nums = [_NUM_HEAD.match(ln.text) for ln in lines]
    cands = [i for i, m in enumerate(nums) if m]
    if not cands:
        return {}
    margin = min(lines[i].x for i in cands)
    chain: dict[int, tuple[str, str | None, Line | None]] = {}
    want, last = 1, -10
    for i, ln in enumerate(lines):
        q = qhits.get(id(ln))
        if q and q[0] == str(want) and not (q[1] or "").lower().startswith("assign"):
            chain[id(ln)] = q
            want, last = want + 1, i
            continue
        m = nums[i]
        if not m or int(m.group(1)) != want or i - last < 3 or ln.x > margin + 8:
            continue
        nxt, prv = (nums[i + 1] if i + 1 < len(lines) else None), (nums[i - 1] if i else None)
        if (nxt and int(nxt.group(1)) == want + 1) or (prv and int(prv.group(1)) == want - 1):
            continue
        rest = m.group("rest").strip()
        code = _rest_line(ln, rest) if rest and code_score(_rest_line(ln, rest)) >= 3 else None
        chain[id(ln)] = (str(want), "Q", code)
        want, last = want + 1, i
    return chain


def _split_programs(lines: list[Line]) -> list[list[Line]]:
    """A document with no headings but several complete programs: a new block starts where
    a program begins (import / class / #include) after the previous one's main has closed."""
    blocks, cur = [], []
    depth, saw_main, ended = 0, False, False
    for ln in lines:
        t = ln.text.strip()
        if ended and _PROGRAM_START.match(t):
            blocks.append(cur)
            cur, depth, saw_main, ended = [], 0, False, False
        cur.append(ln)
        if "static void main" in t or re.search(r"\bint\s+main\s*\(", t):
            saw_main = True
        bare = _STRINGS.sub("", t)
        depth = max(0, depth + bare.count("{") - bare.count("}"))
        if saw_main and depth == 0 and "}" in bare:
            ended = True
    if cur:
        if blocks and not any("main" in ln.text for ln in cur):
            blocks[-1].extend(cur)            # a trailing helper class or output belongs to the last
        else:
            blocks.append(cur)
    return blocks


def segment(lines: list[Line], question_re: str | None = None) -> list[Section]:
    qre = re.compile(question_re or DEFAULT_QUESTION_RE, re.I)
    heads = _find_headings(lines, qre)
    if not heads:
        blocks = _split_programs(lines)
        if len(blocks) >= 2:
            out = []
            for n, block in enumerate(blocks, 1):
                for sec in _segment(block, {}):
                    sec.label, sec.guessed = str(n), True
                    out.append(sec)
            return _merge_same_label(out)
    if not heads:
        heads = {id(ln): (m.group(1), None, None) for ln in lines
                 if (m := qre.match(ln.text.strip())) and not ln.text.strip().endswith((";", "{"))
                 and code_score(ln) < 3}
    sections = _segment(lines, heads)
    if heads and sum(bool(s.code) for s in sections) <= 1:
        # the questions were copied at the top and every answer written below them
        blocks = _split_programs(lines)
        if len(blocks) >= 2:
            unheaded = [[ln for ln in b if id(ln) not in heads] for b in blocks]
            out = []
            for n, block in enumerate(unheaded, 1):
                for sec in _segment(block, {}):
                    sec.label, sec.guessed = str(n), True
                    out.append(sec)
            merged = _merge_same_label(out)
            if sum(bool(s.code) for s in merged) >= 2:
                return merged
    return sections


def _merge_same_label(sections: list[Section]) -> list[Section]:
    out: list[Section] = []
    for sec in sections:
        if out and out[-1].label == sec.label:
            prev = out[-1]
            prev.code += sec.code
            prev.output += sec.output
            prev.output_inline += sec.output_inline
            prev.statement += sec.statement
            prev.code_blocks += sec.code_blocks
        else:
            out.append(sec)
    return out


def _segment(lines: list[Line], heads: dict) -> list[Section]:
    sections: list[Section] = [Section(label="1")]
    started = False
    mode = "none"
    carry = None
    for ln in lines:
        t = ln.text.strip()
        h = heads.get(id(ln))
        if h:
            label, word, code = h[:3]
            sec = Section(label=label, heading_word=word)
            if not started and not (sections[0].statement or sections[0].code):
                sections[0] = sec
            else:
                sections.append(sec)
            started, mode, carry = True, "none", None
            if not (len(h) > 3 and h[3]):            # a heading comment is not part of the code
                sec.statement.append(code or ln)
            continue
        sec = sections[-1]
        if _CODE_MARK.match(t):
            sec.had_code_marker, mode = True, "code"
            continue
        if (cm := _CODE_MARK_INLINE.match(t)):
            sec.had_code_marker, mode = True, "code"
            carry = cm.group("rest").strip()
            continue
        if carry and mode == "code":
            ln, carry = replace(ln, text=carry + " " + ln.text.strip()), None    # "class" + "Circle {"
            t = ln.text
        om = _OUTPUT_MARK.match(t) or _OUTPUT_COMMENT.match(t)
        if om and not _ANNOTATION.match(t):
            sec.had_output_marker, mode = True, "output"
            if (om.group("rest") or "").strip():
                sec.output_inline.append(om.group("rest").strip())
            continue
        if _INPUT_MARK.match(t) and not _ANNOTATION.match(t):
            mode = "input"
            continue
        if mode == "output":
            sec.output.append(ln)
        elif mode == "code":
            sec.code.append(ln)
        elif mode == "input":
            sec.statement.append(ln)
        else:
            sec.statement.append(ln)  # resolved below

    for sec in sections:
        _split_screenshots(sec)
        if sec.had_code_marker:
            sec.code, sec.code_blocks = _pick_code(sec.code, marked=True)
        else:
            picked, sec.code_blocks = _pick_code(sec.statement, marked=False)
            ids = {id(ln) for ln in picked}
            sec.statement = [ln for ln in sec.statement if id(ln) not in ids]
            sec.code = picked
    # drop a leading cover/header section with no code (name, roll no.)
    if len(sections) > 1 and not sections[0].code and not sections[0].output:
        sections = sections[1:]
    return sections
