"""PDF submission -> list of runnable programs, one per question."""
from __future__ import annotations

import re
import statistics
from collections import Counter
from dataclasses import asdict, dataclass, field, replace

from . import cleanup, indent
from .convert import CAPTION, parts_of
from .langdetect import detect_language, java_entrypoint, java_main_class
from .pdfread import Line, read_pdf
from .segment import Section, label_key, segment

LOW_OCR_CONF = 75.0


@dataclass
class ExtractedProgram:
    question: str
    language: str | None
    code: str
    claimed_output: str | None
    entrypoint: str | None = None          # Java class name -> file name
    repairs: dict[str, int] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    pages: list[int] = field(default_factory=list)
    ocr: bool = False
    ocr_confidence: float | None = None
    needs_review: bool = False
    claimed_from_image: bool = False    # the output was read from a screenshot
    source_file: str | None = None      # the attachment it came from, for multi-file submissions
    label_guessed: bool = False         # numbered only by upload order: the grader may place it by topic

    @property
    def filename(self) -> str:
        """File name the sandbox should use (Java needs ClassName.java)."""
        ext = {"python": ".py", "java": ".java", "cpp": ".cpp", "c": ".c"}.get(self.language, ".txt")
        stem = self.entrypoint if self.language == "java" and self.entrypoint else "main"
        return stem + ext


@dataclass
class ExtractionResult:
    source: str
    programs: list[ExtractedProgram] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    ocr_pages: list[int] = field(default_factory=list)
    page_count: int = 0
    repairs: dict[str, int] = field(default_factory=dict)   # document-wide fixes
    images_read: int = 0                                      # screenshots OCR'd

    @property
    def needs_review(self) -> bool:
        return not self.programs or any(p.needs_review for p in self.programs)

    def program(self, question: str) -> ExtractedProgram | None:
        return next((p for p in self.programs if p.question == str(question)), None)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["needs_review"] = self.needs_review
        return d


def _rebuild(lines: list[Line], language: str | None, repairs: Counter,
             warnings: list[str]) -> str:
    """Rebuild indentation, fix auto-capitalisation, and for Python pick the
    indentation strategy that actually compiles."""
    def fix(src: str, rep: Counter) -> str:
        return cleanup.fix_autocapitalisation(src, language, rep)

    rep_exact = Counter()
    exact = fix(indent.rebuild(lines), rep_exact)
    if language != "python":
        repairs.update(rep_exact)
        return exact
    ok, err = indent.python_compiles(exact)
    if ok:
        repairs.update(rep_exact)
        return exact
    rep_lvl = Counter()
    alt = indent.by_levels(lines) if indent.rebuild(lines) != indent.by_levels(lines) else indent.by_width(lines)
    leveled = fix(alt, rep_lvl)
    if indent.python_compiles(leveled)[0]:
        repairs.update(rep_lvl)
        repairs["indentation_rebuilt"] += 1
        warnings.append("indentation rebuilt by the fallback method; check it matches the PDF")
        return leveled
    repairs.update(rep_exact)
    warnings.append(f"Python syntax error after extraction ({err}); "
                    "may be the student's bug or an extraction problem - check the PDF")
    return exact


def _plain(lines: list[Line]) -> str:
    return indent.by_width(lines) if lines else ""


def _claimed(sec: Section) -> tuple[str | None, bool]:
    """The output the student showed for a section, and whether it came from a screenshot."""
    out_parts = list(sec.output_inline)
    out_lines = [ln for ln in sec.output if not (ln.image and cleanup.is_terminal_noise(ln.text))]
    if out_lines:
        out_parts.append(_plain(out_lines))
    claimed = "\n".join(p for p in out_parts if p).strip() or None
    return claimed, any(ln.image for ln in out_lines)


def _program(sec: Section) -> ExtractedProgram | None:
    if not sec.code:
        return None
    repairs = Counter()
    warnings: list[str] = []
    code_lines = cleanup.strip_line_numbers(sec.code, repairs)
    draft = "\n".join(ln.text for ln in code_lines)
    lang, _ = detect_language(draft)
    code = _rebuild(code_lines, lang, repairs, warnings)
    if lang in ("c", "cpp", "java"):
        code = cleanup.join_wrapped_strings(code, repairs)
    if lang == "java":
        code = cleanup.repair_java(code, repairs)
        code = cleanup.hoist_java_imports(code, repairs)
        code = cleanup.drop_java_outside_classes(code, repairs)
    if lang is None:
        warnings.append("language not recognised")
    if sec.code_blocks > 1:
        warnings.append(f"{sec.code_blocks} separate code blocks were joined")
    claimed, from_image = _claimed(sec)
    if claimed is None:
        warnings.append(NO_OUTPUT)

    ocr_lines = [ln for ln in code_lines if ln.ocr]
    conf = statistics.mean(ln.conf for ln in ocr_lines) if ocr_lines else None
    prog = ExtractedProgram(
        question=sec.label, language=lang, code=code.rstrip() + "\n",
        claimed_output=claimed,
        entrypoint=java_entrypoint(code) if lang == "java" else None,
        repairs=dict(repairs),
        warnings=warnings,
        pages=sorted({ln.page for ln in code_lines}),
        ocr=bool(ocr_lines), ocr_confidence=round(conf, 1) if conf is not None else None,
        claimed_from_image=from_image,
        label_guessed=sec.guessed,
    )
    if lang == "java" and not prog.entrypoint:
        warnings.append("Java class name not found")
    if ocr_lines:
        warnings.append(f"read by OCR (confidence {conf:.0f}%): check digits and "
                        "symbols against the PDF before trusting the result")
    _set_review(prog)
    return prog


def _set_review(prog: ExtractedProgram) -> None:
    prog.needs_review = (
        prog.language is None
        or prog.ocr   # OCR can silently turn `1` into `13`
        or any("syntax error" in w or "not found" in w for w in prog.warnings)
    )


NO_OUTPUT = "no 'Output' section found in the PDF"


def extract_submission(pdf_path: str, *, ocr: str = "auto",
                       question_re: str | None = None) -> ExtractionResult:
    rd = read_pdf(pdf_path, ocr=ocr)
    res = ExtractionResult(source=str(pdf_path), warnings=list(rd.warnings),
                           ocr_pages=rd.ocr_pages, page_count=rd.page_count)
    doc_repairs: Counter = Counter()
    # captions added when converting a standalone attachment are not content
    lines = [ln for ln in rd.lines if not ln.text.startswith(CAPTION)]
    lines = cleanup.normalize_lines(lines, doc_repairs)
    lines = cleanup.remove_headers_footers(lines, doc_repairs)
    res.repairs = dict(doc_repairs)
    res.images_read = rd.images_read
    if not lines:
        res.warnings.append("no text found (empty PDF, or scanned page and OCR unavailable)")
        return res

    parts = parts_of(pdf_path)
    if parts:
        res.programs = _from_parts(lines, parts, question_re, res)
    else:
        for sec in segment(lines, question_re):
            prog = _program(sec)
            if prog:
                res.programs.append(prog)
            elif sec.had_code_marker or sec.had_output_marker:
                res.warnings.append(f"question {sec.label}: no code found")
    if not res.programs:
        res.warnings.append("no code found in the PDF")
    return res


# ------------------------------------------------------------------ one answer per attached file
QUESTION_WORDS = {"q", "qn", "qs", "ques", "question", "problem", "prob", "program", "prog",
                  "experiment", "expt", "exp", "task", "exercise", "ex"}
# "1." / "3.." / "Q2" alone on one of the first lines of a file
_NUMBER_LINE = re.compile(r"^\s*(?:(?:q|qn|ques|question|prog|program)\s*\.?\s*)?(\d{1,2})\s*[.):\-]*\s*$", re.I)
# q2.java, ass1q3, Question_4, "KA 3" (Hindi "of": "assignment 1 ka 3" = its question 3)
_NAME_QUESTION = re.compile(r"(?:^|[^a-z])(?:q|qn|qs|ques|question|prog|program|ex|exp|task|ka)"
                            r"[\s_.\-#]*(\d{1,2})(?!\d)", re.I)
_MARKER = re.compile(r"^\s*(code|output)\s*:\s*$", re.I)


def _stem(name: str) -> str:
    base = name.rsplit("/", 1)[-1]
    return base.rsplit(".", 1)[0] if "." in base else base


def _name_question(name: str) -> str | None:
    m = _NAME_QUESTION.search(_stem(name))
    return str(int(m.group(1))) if m and int(m.group(1)) else None


def _name_last_number(name: str) -> str | None:
    stem = re.sub(r"\d{3,}", " ", _stem(name))      # roll numbers, years
    nums = [n for n in re.findall(r"(?<!\d)(\d{1,2})(?!\d)", stem) if int(n)]
    return str(int(nums[-1])) if nums else None


def _content_number(lines: list[Line]) -> str | None:
    head = [ln for ln in lines if not _MARKER.match(ln.text)][:3]
    for ln in head:
        m = _NUMBER_LINE.match(ln.text)
        if m and int(m.group(1)):
            return str(int(m.group(1)))
    return None


def _trailing_output(sec: Section, plines: list[Line]) -> None:
    """In a code file, lines after the last line of code are the output pasted below it."""
    if sec.output or sec.output_inline or not sec.code:
        return
    picked = {id(ln) for ln in sec.code}
    last = max(i for i, ln in enumerate(plines) if id(ln) in picked)
    tail = [ln for ln in plines[last + 1:] if id(ln) not in picked and not _MARKER.match(ln.text)]
    if tail:
        sec.output = tail
        sec.had_output_marker = True


@dataclass
class _Part:
    name: str
    kind: str
    lines: list[Line]
    programs: list[ExtractedProgram] = field(default_factory=list)
    sections: list[Section] = field(default_factory=list)
    outputs: list[tuple[str, bool]] = field(default_factory=list)


def _merge_java(host: ExtractedProgram, helper: ExtractedProgram) -> None:
    """Put a helper class (no main) in the same file as the program using it, imports first."""
    imports, body = [], []
    for code in (host.code, helper.code):
        part = []
        for ln in code.rstrip("\n").split("\n"):
            if re.match(r"\s*import\s+[\w.*]+\s*;", ln):
                if ln.strip() not in imports:
                    imports.append(ln.strip())
            elif not re.match(r"\s*package\s+[\w.]+\s*;", ln):
                part.append(ln)
        while part and not part[0].strip():
            part.pop(0)
        body.append("\n".join(part))
    host.code = ("\n".join(imports) + "\n\n" if imports else "") + "\n\n".join(body).rstrip() + "\n"
    host.entrypoint = java_entrypoint(host.code)
    host.pages = sorted(set(host.pages) | set(helper.pages))
    for k, v in helper.repairs.items():
        host.repairs[k] = host.repairs.get(k, 0) + v
    host.ocr = host.ocr or helper.ocr
    host.warnings.append(f"class {java_entrypoint(helper.code)} from another file was added to this program")
    _set_review(host)


def _from_parts(lines: list[Line], parts: list[dict], question_re: str | None,
                res: ExtractionResult) -> list[ExtractedProgram]:
    found: list[_Part] = []
    first = 0
    for p in parts:
        last = first + int(p.get("pages") or 0)
        plines = [ln for ln in lines if first < ln.page <= last]
        first = last
        part = _Part(name=str(p.get("name") or ""), kind=str(p.get("kind") or ""), lines=plines)
        if part.kind == "text":   # every line of a text file is monospaced: judge lines by content
            plines = part.lines = [replace(ln, mono=False) for ln in plines]
        part.sections = segment(plines, question_re) if plines else []
        for sec in part.sections:
            if part.kind == "text" and len(part.sections) == 1:
                _trailing_output(sec, plines)
            prog = _program(sec)
            if prog:
                prog.source_file = part.name
                part.programs.append(prog)
            else:
                claimed, from_image = _claimed(sec)
                if claimed:
                    part.outputs.append((claimed, from_image))
        if (len(parts) >= 2 and len(part.programs) >= 2 and not _is_question_document(part)
                and not all(p.label_guessed for p in part.programs)):   # pieces split at program ends stay apart
            _collapse(part)
        if not part.programs and not part.outputs and plines:
            res.warnings.append(f"{part.name}: no code or output found")
        found.append(part)

    _join_java_helpers(found)
    _merge_duplicates(found)
    _match_photos(found)
    fixed = _number_from_document(found)
    coded = [p for p in found if p.programs]
    if len(coded) >= 2:
        _label_by_file(coded, fixed)

    programs = [prog for p in found for prog in p.programs]
    for i, part in enumerate(found):
        for text, from_image in part.outputs:
            _attach_output(programs, found, i, text, from_image)
    seen: set[str] = set()
    for prog in programs:                 # a question number is never used twice
        if prog.question in seen:
            n = 1
            while str(n) in seen or any(q.question == str(n) for q in programs):
                n += 1
            prog.warnings.append(f"another file also looked like question {prog.question}")
            prog.question = str(n)
            prog.label_guessed = True
        seen.add(prog.question)
    return sorted(programs, key=lambda p: (label_key(p.question), p.question))


def _is_question_document(part: _Part) -> bool:
    """Two or more different real headings ("Q1", "Question 2"…) with code under them."""
    labels = {s.label for s in part.sections
              if s.code and (s.heading_word or "").lower() in QUESTION_WORDS | {"assignment"}}
    return len(labels) >= 2


def _collapse(part: _Part) -> None:
    """A one-answer file that a stray heading (often OCR noise) split in pieces."""
    first, *rest = part.programs
    for prog in rest:
        first.code = first.code.rstrip("\n") + "\n\n" + prog.code
        if prog.claimed_output:
            first.claimed_output = (first.claimed_output + "\n" if first.claimed_output else "") + prog.claimed_output
            first.claimed_from_image = first.claimed_from_image or prog.claimed_from_image
            if NO_OUTPUT in first.warnings:
                first.warnings.remove(NO_OUTPUT)
        first.pages = sorted(set(first.pages) | set(prog.pages))
        first.ocr = first.ocr or prog.ocr
        first.language = first.language or prog.language
    if first.language == "java":
        first.entrypoint = java_entrypoint(first.code)
    _set_review(first)
    part.programs = [first]


# ------------------------------------------------------------------ the same answer in two files
_JAVA_C_WORDS = {"public", "private", "protected", "static", "void", "int", "double", "float", "long", "char",
                 "boolean", "string", "class", "new", "return", "this", "system", "out", "println", "print",
                 "printf", "if", "else", "for", "while", "args", "main", "include", "stdio", "h", "scanf",
                 "import", "java", "util", "scanner", "in", "def", "self", "range", "input"}


def _tokens(code: str) -> Counter:
    return Counter(t for t in re.findall(r"[a-z_][a-z0-9_]*|\d+", code.lower()) if t not in _JAVA_C_WORDS)


def _similarity(a: str, b: str) -> float:
    ta, tb = _tokens(a), _tokens(b)
    both = sum((ta | tb).values())
    return sum((ta & tb).values()) / both if both else 0.0


def _rank(part: _Part, prog: ExtractedProgram) -> int:
    """Which copy of an answer to trust: a code file, then typed documents, then OCR."""
    if prog.ocr:
        return 2
    return 0 if part.kind == "text" else 1


def _absorb(keep: ExtractedProgram, drop: ExtractedProgram, drop_name: str) -> None:
    if not keep.claimed_output and drop.claimed_output:
        keep.claimed_output, keep.claimed_from_image = drop.claimed_output, drop.claimed_from_image
        if NO_OUTPUT in keep.warnings:
            keep.warnings.remove(NO_OUTPUT)
    keep.warnings.append(f"the same code was also in {drop_name.rsplit('/', 1)[-1]}")


def _merge_duplicates(found: list[_Part]) -> None:
    """Near-identical code in two files (Main.java and Main.javax, a code file and a photo
    of it, a Word file and its PDF printout) is one answer."""
    def headed(p):
        return len(p.programs) >= 2 and not all(x.label_guessed for x in p.programs)

    progs = [(p, prog, headed(p)) for p in found for prog in p.programs]
    gone: set[int] = set()
    for i, (pa, a, ha) in enumerate(progs):
        for pb, b, hb in progs[i + 1:]:
            # a loose file against a headed document is left to _number_from_document
            if pa is pb or ha != hb or id(a) in gone or id(b) in gone:
                continue
            if _similarity(a.code, b.code) < 0.85:
                continue
            (kp, keep), (dp, drop) = ((pa, a), (pb, b)) if _rank(pa, a) <= _rank(pb, b) else ((pb, b), (pa, a))
            if keep.label_guessed and not drop.label_guessed:      # keep the stated question number
                keep.question, keep.label_guessed = drop.question, False
            _absorb(keep, drop, dp.name)
            dp.programs.remove(drop)
            gone.add(id(drop))


def _match_photos(found: list[_Part]) -> None:
    """A photo or screenshot of code (read by OCR, often cropped) next to the code files
    is a picture of one of them: matched by name (ATM.png -> ATM.java) or as the clear
    best match. The code file's exact text is graded; any output in the photo is kept."""
    singles = [p for p in found if len(p.programs) == 1]
    photos = [p for p in singles if p.programs[0].ocr]
    files = [p for p in singles if not p.programs[0].ocr]
    if not photos or not files:
        return
    sim = [[_similarity(ph.programs[0].code, f.programs[0].code) for f in files] for ph in photos]

    def second(values, skip):
        rest = [v for j, v in enumerate(values) if j != skip]
        return max(rest) if rest else 0.0

    pairs = []
    for i, ph in enumerate(photos):
        for j, f in enumerate(files):
            if _stem(ph.name).lower() == _stem(f.name).lower():
                pairs.append((2.0, i, j))
            elif (sim[i][j] >= 0.25 and sim[i][j] >= 1.3 * second(sim[i], j)
                  and sim[i][j] >= 1.3 * second([row[j] for row in sim], i)):
                pairs.append((sim[i][j], i, j))
    used_p, used_f = set(), set()
    for _, i, j in sorted(pairs, reverse=True):
        if i in used_p or j in used_f:
            continue
        used_p.add(i)
        used_f.add(j)
        keep, drop = files[j].programs[0], photos[i].programs[0]
        if not keep.claimed_output and drop.claimed_output:
            keep.claimed_output, keep.claimed_from_image = drop.claimed_output, drop.claimed_from_image
            if NO_OUTPUT in keep.warnings:
                keep.warnings.remove(NO_OUTPUT)
        keep.warnings.append(f"a photo of this code was also attached ({photos[i].name.rsplit('/', 1)[-1]})")
        photos[i].programs = []


def _number_from_document(found: list[_Part]) -> set[int]:
    """If one file holds the whole assignment with numbered questions, it is the key: each
    separate answer (a code file, or a piece of a document with no headings) takes the number
    of the document answer its code matches best (students often paste a revised version in
    the report, so the match is relative, helped by the file's own number). Only one copy is
    graded: for the same code, the better copy with the output the student showed; for two
    different versions, the one that comes with its own shown output, flagged for review."""
    def headed(p):
        return len(p.programs) >= 2 and not all(x.label_guessed for x in p.programs)

    keyed = [(p, prog) for p in found if headed(p) for prog in p.programs]
    fixed = {id(prog) for _, prog in keyed}
    if not keyed:
        return fixed
    loose = [(p, prog) for p in found if not headed(p) for prog in p.programs]
    sim = [[_similarity(lp.code, k.code) for _, k in keyed] for _, lp in loose]
    named = [(_content_number(p.lines) or _name_question(p.name)) if len(p.programs) == 1 else None
             for p, _ in loose]

    def second(values, skip):
        rest = [v for j, v in enumerate(values) if j != skip]
        return max(rest) if rest else 0.0

    pairs = []
    for si in range(len(loose)):
        for ki, (_, k) in enumerate(keyed):
            v = sim[si][ki]
            score = v + (0.3 if named[si] == k.question else 0.0)
            clear = (v >= 0.15 and v >= 1.5 * second(sim[si], ki)
                     and v >= 1.5 * second([row[ki] for row in sim], si))
            if score >= 0.5 or clear:
                pairs.append((score, si, ki))
    used_s, used_k = set(), set()
    for _, si, ki in sorted(pairs, reverse=True):
        if si in used_s or ki in used_k:
            continue
        used_s.add(si)
        used_k.add(ki)
        spart, sprog = loose[si]
        kpart, kprog = keyed[ki]
        same = sim[si][ki] >= 0.85
        if same:
            s_wins = _rank(spart, sprog) <= _rank(kpart, kprog)
        else:
            if sprog.ocr != kprog.ocr:
                # a screenshot read by OCR differs from the typed copy by its misreadings too:
                # the typed copy is graded, with the output the screenshot's page showed
                s_wins = kprog.ocr
                w, l = (sprog, kprog) if s_wins else (kprog, sprog)
                if not w.claimed_output and l.claimed_output:
                    w.claimed_output, w.claimed_from_image = l.claimed_output, l.claimed_from_image
                    if NO_OUTPUT in w.warnings:
                        w.warnings.remove(NO_OUTPUT)
            else:
                s_wins = (bool(sprog.claimed_output), -_rank(spart, sprog)) >= (bool(kprog.claimed_output), -_rank(kpart, kprog))
            loser = kpart if s_wins else spart
            winner = sprog if s_wins else kprog
            winner.warnings.append(f"{loser.name.rsplit('/', 1)[-1]} has a different version of this answer; "
                                   "this one was graded")
            winner.needs_review = True
        if s_wins:
            sprog.question, sprog.label_guessed = kprog.question, False
            if same:
                _absorb(sprog, kprog, kpart.name)
            kpart.programs.remove(kprog)
            fixed.add(id(sprog))
        else:
            if same:
                _absorb(kprog, sprog, spart.name)
            spart.programs.remove(sprog)
    return fixed


def _join_java_helpers(found: list[_Part]) -> None:
    singles = [p for p in found if len(p.programs) == 1 and p.programs[0].language == "java"]
    for part in singles:
        helper = part.programs[0]
        if helper.ocr or java_main_class(helper.code):     # a photo is never a helper class
            continue
        name = java_entrypoint(helper.code)
        hosts = [p for p in singles if p is not part and p.programs and not p.programs[0].ocr
                 and java_main_class(p.programs[0].code)]
        users = [p for p in hosts if name and re.search(rf"\b{re.escape(name)}\b", p.programs[0].code)]
        if not users:
            continue
        idx = found.index(part)
        host = min(users, key=lambda p: (found.index(p) < idx, abs(found.index(p) - idx)))
        _merge_java(host.programs[0], helper)
        part.programs = []


def _label_by_file(coded: list[_Part], fixed: set[int]) -> None:
    """Each file is one answer: number it from its content ("2."), its name (q2.java,
    "assignment 1 ka 2"), a "Question 2" heading, or else the order it was attached in."""
    used = {prog.question for p in coded for prog in p.programs if id(prog) in fixed}
    todo = [p for p in coded if len(p.programs) == 1 and id(p.programs[0]) not in fixed]
    labels: list[str | None] = []
    for part in todo:
        sec = next((s for s in part.sections if s.code), None)
        heading = sec.label if sec and (sec.heading_word or "").lower() in QUESTION_WORDS else None
        labels.append(_content_number(part.lines) or _name_question(part.name) or heading)
    lasts = [_name_last_number(p.name) for p in todo]
    if todo and all(lasts) and len(set(lasts)) == len(lasts):
        labels = [lab or last for lab, last in zip(labels, lasts)]

    for i, (part, lab) in enumerate(zip(todo, labels)):
        if lab in used:
            part.programs[0].warnings.append(f"another file also looked like question {lab}")
            labels[i] = None
        elif lab:
            used.add(lab)
    n = 1
    for part, lab in zip(todo, labels):
        if lab is None:
            while str(n) in used:
                n += 1
            lab = str(n)
            used.add(lab)
            part.programs[0].label_guessed = True
        part.programs[0].question = lab


def _attach_output(programs: list[ExtractedProgram], found: list[_Part], i: int,
                   text: str, from_image: bool) -> None:
    """An output-only file (output.txt, a screenshot) belongs to the question its name
    points to, else to the answer just before it, else the one after."""
    part = found[i]
    by_label = {p.question: p for p in programs}
    target = None
    same_name = [f for f in found if f.programs and f is not part
                 and _stem(f.name).lower() == _stem(part.name).lower()]
    if same_name:
        target = same_name[0].programs[0]
    for lab in (_name_question(part.name), _content_number(part.lines), _name_last_number(part.name)):
        if target is None and lab in by_label:
            target = by_label[lab]
            break
    if target is None:
        before = [p for f in found[:i] for p in f.programs]
        after = [p for f in found[i + 1:] for p in f.programs]
        target = before[-1] if before else (after[0] if after else None)
    if target is None:
        return
    target.claimed_output = (target.claimed_output + "\n" + text) if target.claimed_output else text
    target.claimed_from_image = target.claimed_from_image or from_image
    if NO_OUTPUT in target.warnings:
        target.warnings.remove(NO_OUTPUT)
