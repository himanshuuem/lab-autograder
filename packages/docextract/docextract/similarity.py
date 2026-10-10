"""Code-similarity check (winnowing, the algorithm behind MOSS).

Programs are tokenised with comments and whitespace dropped, user-chosen names
replaced by V, numbers by N and strings by S, so renaming variables or
reformatting does not hide a copy. Fingerprints shared by a large part of the
class (textbook patterns) and fingerprints of the teacher's starter code are
ignored. Results flag pairs for a human to judge; they are not proof.
"""
from __future__ import annotations

import hashlib
import re
from collections import Counter
from dataclasses import dataclass, field
from itertools import combinations

KEYWORDS = set("""
and as assert async await break case catch char class const continue def default del
delete do double elif else enum except extends false False final finally float for from
global goto if implements import in int interface is lambda long namespace new None
nonlocal not null or package pass private protected public raise return short signed
sizeof static struct switch template this throw throws true True try typedef typename
union unsigned using virtual void volatile while with yield bool auto boolean byte string
""".split())
# library names keep their identity: copying `printf` is not suspicious, but they
# carry structure that should still match between two copies
LIBRARY = set("""
print input range len int str float list dict set tuple map sorted sum min max abs
append pop insert split strip join open enumerate zip printf scanf puts gets malloc
calloc realloc free strlen strcpy strcmp strcat sqrt pow cout cin endl std vector
push_back size begin end sort swap main System out println print Scanner nextInt
nextLine next String Math length charAt ArrayList add get include stdio stdlib iostream
math string bits stdc NULL nullptr exit getline
""".split())
# names that are never a student's own variable
ALWAYS_LITERAL = set("""cout cin endl std System NULL nullptr include stdio stdlib iostream
bits stdc String Scanner main printf scanf print input range len""".split())
_NEXT_PAREN = re.compile(r"\s*\(")

_TOKEN = re.compile(r"""
    (?P<str>"(?:\\.|[^"\\\n])*"|'(?:\\.|[^'\\\n])*')
  | (?P<num>\b\d+(?:\.\d+)?(?:[eE][-+]?\d+)?[lLfFuU]*\b|\b0[xX][0-9a-fA-F]+\b)
  | (?P<id>[A-Za-z_]\w*)
  | (?P<op><<=|>>=|==|!=|<=|>=|&&|\|\||\+\+|--|->|::|<<|>>|\+=|-=|\*=|/=|%=|\*\*|//|[^\s\w])
""", re.X)


def _strip_comments(code: str, language: str | None) -> str:
    def blank(m):  # keep newlines so line numbers stay correct
        return re.sub(r"[^\n]", " ", m.group(0))
    if language == "python":
        code = re.sub(r'"""[\s\S]*?"""|\'\'\'[\s\S]*?\'\'\'', blank, code)
        code = re.sub(r"#[^\n]*", blank, code)
    else:
        code = re.sub(r"/\*[\s\S]*?\*/", blank, code)
        code = re.sub(r"//[^\n]*", blank, code)
    return code


def tokenize(code: str, language: str | None = None) -> list[tuple[str, int]]:
    """Return (normalised token, 1-based line number)."""
    code = _strip_comments(code, language)
    out = []
    line_starts = [0] + [i + 1 for i, c in enumerate(code) if c == "\n"]
    import bisect
    prev = None
    for m in _TOKEN.finditer(code):
        kind = m.lastgroup
        tok = raw = m.group(0)
        if language != "python" and kind == "op" and tok == "#":
            continue
        if kind == "str":
            tok = "S"
        elif kind == "num":
            tok = "N"
        elif kind == "id" and tok not in KEYWORDS:
            # a library name stays literal only when used as one: `len(x)`,
            # `v.size()`, `std::sort`; a variable called `size` becomes V
            used_as_library = tok in ALWAYS_LITERAL or (tok in LIBRARY and (
                prev in (".", "::", "->") or _NEXT_PAREN.match(code, m.end())))
            if not used_as_library:
                tok = "V"
        out.append((tok, bisect.bisect_right(line_starts, m.start())))
        prev = raw
    return out


def _h(gram: tuple[str, ...]) -> int:
    return int.from_bytes(hashlib.blake2b("\x1f".join(gram).encode(), digest_size=8).digest(), "big")


def fingerprints(tokens: list[tuple[str, int]], k: int = 8, w: int = 4) -> dict[int, list[tuple[int, int]]]:
    """Winnowing: hash -> list of (first line, last line) spans it covers."""
    if len(tokens) < k:
        if not tokens:
            return {}
        return {_h(tuple(t for t, _ in tokens)): [(tokens[0][1], tokens[-1][1])]}
    hashes = [(_h(tuple(t for t, _ in tokens[i:i + k])), i) for i in range(len(tokens) - k + 1)]
    picked: dict[int, list[tuple[int, int]]] = {}
    last = None
    for s in range(max(1, len(hashes) - w + 1)):
        win = hashes[s:s + w]
        hv, pos = min(reversed(win), key=lambda t: t[0])  # rightmost minimum
        if (hv, pos) != last:
            picked.setdefault(hv, []).append((tokens[pos][1], tokens[pos + k - 1][1]))
            last = (hv, pos)
    return picked


@dataclass
class Doc:
    id: str                      # student name / roll no. / file name
    code: str
    language: str | None = None


@dataclass
class PairResult:
    a: str
    b: str
    score: float                 # shared / smaller fingerprint set, 0..1
    jaccard: float
    shared: int
    lines_a: list[tuple[int, int]] = field(default_factory=list)
    lines_b: list[tuple[int, int]] = field(default_factory=list)
    low_confidence: bool = False   # program too short to judge


def _merge(spans: list[tuple[int, int]]) -> list[tuple[int, int]]:
    out: list[list[int]] = []
    for a, b in sorted(spans):
        if out and a <= out[-1][1] + 1:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return [tuple(x) for x in out]


def compare_submissions(docs: list[Doc], *, k: int = 8, w: int = 4,
                        starter_code: str | None = None, common_frac: float = 0.4,
                        threshold: float = 0.5, min_fingerprints: int = 8) -> list[PairResult]:
    """Compare every pair (same language only). Returns pairs with
    score >= threshold, most similar first."""
    fps = {d.id: fingerprints(tokenize(d.code, d.language), k, w) for d in docs}
    ignore: set[int] = set()
    if starter_code:
        langs = {d.language for d in docs} or {None}
        for lang in langs:
            ignore |= set(fingerprints(tokenize(starter_code, lang), k, w))
    if len(docs) >= 5:
        counts = Counter(h for f in fps.values() for h in f)
        ignore |= {h for h, c in counts.items() if c / len(docs) > common_frac}
    sets = {i: set(f) - ignore for i, f in fps.items()}

    results = []
    for da, db in combinations(docs, 2):
        if da.language and db.language and da.language != db.language:
            continue
        sa, sb = sets[da.id], sets[db.id]
        if not sa or not sb:
            continue
        common = sa & sb
        score = len(common) / min(len(sa), len(sb))
        if score < threshold:
            continue
        results.append(PairResult(
            a=da.id, b=db.id, score=round(score, 3),
            jaccard=round(len(common) / len(sa | sb), 3), shared=len(common),
            lines_a=_merge([sp for h in common for sp in fps[da.id][h]]),
            lines_b=_merge([sp for h in common for sp in fps[db.id][h]]),
            low_confidence=min(len(sa), len(sb)) < min_fingerprints,
        ))
    results.sort(key=lambda r: (-r.score, -r.shared))
    return results
