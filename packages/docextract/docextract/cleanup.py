"""Undo the damage word processors do to pasted code.

Every change is counted in a `repairs` dict so the TA can see exactly what
was altered before the code was run. Nothing here changes program logic.
"""
from __future__ import annotations

import re
from collections import Counter

from .pdfread import Line

CHAR_MAP = {
    "\u2018": "'", "\u2019": "'", "\u201a": "'", "\u201b": "'", "\u2032": "'",
    "\u201c": '"', "\u201d": '"', "\u201e": '"', "\u201f": '"', "\u2033": '"',
    "\u00ab": '"', "\u00bb": '"',
    "\u2013": "-", "\u2014": "-", "\u2212": "-", "\u2010": "-", "\u2011": "-",
    "\u00a0": " ", "\u2009": " ", "\u202f": " ", "\u2007": " ", "\u3000": " ",
    "\u2026": "...",
    "\ufb00": "ff", "\ufb01": "fi", "\ufb02": "fl", "\ufb03": "ffi", "\ufb04": "ffl",
    "\u2264": "<=", "\u2265": ">=", "\u2260": "!=",
}
ZERO_WIDTH = "\u200b\u200c\u200d\u2060\ufeff\u00ad"
_ZW_RE = re.compile(f"[{ZERO_WIDTH}]")

_PAGE_NO = re.compile(r"^(page\s*)?\d{1,3}(\s*(of|/)\s*\d{1,3})?$", re.I)
_LEAD_NUM = re.compile(r"^(\d{1,4})[.:)|]?\s+")


def normalize_text(s: str, repairs: Counter) -> str:
    out = []
    for ch in s:
        rep = CHAR_MAP.get(ch)
        if rep is not None:
            kind = ("smart_quote" if rep in ("'", '"') else
                    "dash" if rep == "-" else
                    "special_space" if rep == " " else
                    "ligature" if rep.isalpha() else "symbol")
            repairs[kind] += 1
            out.append(rep)
        else:
            out.append(ch)
    s = "".join(out)
    s, n = _ZW_RE.subn("", s)
    if n:
        repairs["zero_width_char"] += n
    return s


def normalize_lines(lines: list[Line], repairs: Counter) -> list[Line]:
    for ln in lines:
        ln.text = normalize_text(ln.text, repairs).rstrip()
    return [ln for ln in lines if ln.text.strip()]


def remove_headers_footers(lines: list[Line], repairs: Counter,
                           band: float = 0.07) -> list[Line]:
    """Drop page numbers, and text repeated in the top/bottom band of most pages
    (e.g. a name/roll-number header). Code lines in the body are never touched."""
    pages = {ln.page for ln in lines}
    in_band = lambda ln: ln.y < ln.page_h * band or ln.y > ln.page_h * (1 - band)
    band_counts = Counter()
    for p in pages:
        for t in {ln.text.strip() for ln in lines if ln.page == p and in_band(ln)}:
            band_counts[t] += 1
    repeated = {t for t, c in band_counts.items()
                if len(pages) >= 2 and c >= max(2, 0.6 * len(pages))}
    kept = []
    for ln in lines:
        t = ln.text.strip()
        if in_band(ln) and (t in repeated or _PAGE_NO.match(t)):
            repairs["header_footer_removed"] += 1
            continue
        kept.append(ln)
    return kept


def strip_line_numbers(lines: list[Line], repairs: Counter) -> list[Line]:
    """Remove IDE line numbers ('1  #include ...', '2  int main') if most lines
    of the block carry increasing numbers."""
    if len(lines) < 3:
        return lines
    nums = [(_LEAD_NUM.match(ln.text), ln) for ln in lines]
    numbered = [(int(m.group(1)), ln) for m, ln in nums if m]
    if len(numbered) < 0.7 * len(lines):
        return lines
    seq = [n for n, _ in numbered]
    increasing = sum(1 for a, b in zip(seq, seq[1:]) if b > a)
    if increasing < 0.8 * (len(seq) - 1) or seq[0] > 5:
        return lines
    for m, ln in nums:
        if m:
            ln.text = ln.text[m.end():]
            if ln.x_after_num is not None:
                ln.x = ln.x_after_num
            repairs["line_number_removed"] += 1
    return [ln for ln in lines if ln.text.strip()]


# Word processors capitalise the first letter of a "sentence". In code that
# turns `int main` into `Int main` and `print(` into `Print(`.
_CAP_PY = re.compile(
    r"^(\s*)(Def|If|Elif|Else|For|While|Return|Import|From|Print|Try|Except|"
    r"Finally|With|Pass|Break|Continue|Input|Class|Global|Lambda|Assert|Raise|"
    r"Range|Len)(?=[\s(:.])")
_CAP_C = re.compile(
    r"^(\s*)(Int|Void|Float|Double|Char|Long|Short|Unsigned|Bool|Return|For|If|"
    r"Else|While|Do|Switch|Case|Break|Continue|Printf|Scanf|Cout|Cin|Using|"
    r"Struct|Typedef|Const|Static|Public|Private|Protected|Class|Import|Package|"
    r"Try|Catch|Throw|New|Delete|Free|Malloc|Puts|Gets|Template|Auto|Super)(?=[\s(<{:;*&])")


def fix_autocapitalisation(code: str, language: str | None, repairs: Counter) -> str:
    rx = _CAP_PY if language == "python" else _CAP_C if language in ("c", "cpp", "java") else None
    if rx is None:
        return code
    out = []
    # a class the student named Auto, Delete or Template keeps its capital (Word may
    # have capitalised the keyword too: `Class Auto extends Vehicle`)
    classes = set(re.findall(r"\b(?:[Cc]lass|[Ii]nterface|[Ee]num|[Ss]truct)\s+([A-Z]\w*)", code))
    for line in code.split("\n"):
        m = rx.match(line)
        if m:
            word = m.group(2)
            # Java: `Class<?>` is a real type; leave it alone
            if word not in classes and not (language == "java" and word == "Class" and line[m.end():].startswith("<")):
                line = m.group(1) + word.lower() + line[m.end():]
                repairs["auto_capital_fixed"] += 1
        out.append(line)
    return "\n".join(out)


# Lines a terminal or IDE shows around a program's output. Removed from output
# read out of screenshots, so only what the program printed is compared.
_NOISE = [
    re.compile(r"^\s*[$#>%]\s*$"),                                         # bare prompt
    re.compile(r"^\s*(\$|>>?>?)\s+\S"),                                     # $ ./a.out, >>> x
    # a command line, even when OCR misreads the prompt ($ -> ¢, §, S)
    re.compile(r"^\s*\S?\s*(\./[\w.-]+(\s|$)|javac?\s+[\w.]+(\.java)?\s*$|python3?\s+\S+\.py\b"
               r"|(gcc|g\+\+|clang)\s+\S+\.(c|cpp|cc)\b)"),
    re.compile(r"^\s*[\w.-]+@[\w.-]+.*[$#%]"),                               # user@host:~$
    re.compile(r"^\s*(PS\s+)?[A-Za-z]:\\[^>]*>"),                             # C:\Users\x> / PS C:\>
    re.compile(r"(\\|/)(bin|Program Files)(\\|/).*(java|python|javaw)(\.exe)?\b", re.I),
    re.compile(r"process finished with exit code", re.I),
    re.compile(r"program finished with exit code", re.I),
    re.compile(r"press (enter|any key) to (exit|continue)", re.I),
    re.compile(r"^\s*(build (successful|failed)|total time:)", re.I),
    re.compile(r"^\s*-{6,}\s*$"),
    re.compile(r"^\s*[eoOcC°•●○©@®0.:*]{2,6}\s{2,}\S"),        # title bar: OCR'd window buttons + title
    re.compile(r"^\s*run\s*:\s*\w+\s*$", re.I),                    # IntelliJ "Run: Main" tab
    re.compile(r"(terminal|console|command prompt|powershell|cmd\.exe|run:|output|zsh|bash)\s*$", re.I),
]


def is_terminal_noise(text: str) -> bool:
    t = text.strip()
    if not t:
        return True
    if any(rx.search(t) for rx in _NOISE[:-1]):
        return True
    # window title bar: a short line ending in a window name, often with OCR'd traffic lights
    return bool(_NOISE[-1].search(t)) and len(t.split()) <= 5 and not re.search(r"\d", t)


def _ends_inside_string(line: str) -> bool:
    """True if a C/C++/Java line ends with a "..." string still open (ignoring comments
    and character literals such as '"')."""
    if '"""' in line:
        return False
    i, n, in_str = 0, len(line), False
    while i < n:
        ch = line[i]
        if in_str:
            if ch == "\\":
                i += 2
                continue
            if ch == '"':
                in_str = False
        elif ch == '"':
            in_str = True
        elif ch == "'":
            end = line.find("'", i + 1 + (line[i + 1:i + 2] == "\\"))
            i = end if 0 < end <= i + 4 else i
        elif line.startswith("//", i) or line.startswith("/*", i):
            return False
        i += 1
    return in_str


def join_wrapped_strings(code: str, repairs: Counter) -> str:
    """Rejoin a line the page width broke inside a string literal, e.g.
        System.out.println("Brand: " + b + "
        Maxspeed: " + s);
    (a line can't end inside a string in C, C++ or Java, so this is always a wrap)."""
    lines = code.split("\n")
    out, i = [], 0
    while i < len(lines):
        line, joins = lines[i], 0
        while _ends_inside_string(line) and joins < 3:
            j = i + 1
            while j < len(lines) and not lines[j].strip() and j - i <= 2:
                j += 1
            if j >= len(lines) or not lines[j].strip():
                break
            line = line.rstrip() + " " + lines[j].strip()
            i, joins = j, joins + 1
        if joins:
            repairs["wrapped_line_joined"] += joins
        out.append(line)
        i += 1
    return "\n".join(out)


_IMPORT = re.compile(r"^\s*import\s+(?:static\s+)?[\w.]+(?:\.\*)?\s*;\s*$")


def hoist_java_imports(code: str, repairs: Counter) -> str:
    """Two programs joined into one answer leave the second one's imports in the middle,
    which Java rejects; imports belong at the top (duplicates dropped)."""
    lines = code.split("\n")
    first_code = next((i for i, ln in enumerate(lines) if ln.strip() and not _IMPORT.match(ln)
                       and not ln.strip().startswith(("//", "/*", "*", "package "))), len(lines))
    late = [i for i, ln in enumerate(lines) if i > first_code and _IMPORT.match(ln)]
    if not late:
        return code
    head = [ln.strip() for ln in lines[:first_code] if _IMPORT.match(ln)]
    for i in late:
        if lines[i].strip() not in head:
            head.append(lines[i].strip())
    rest = [ln for i, ln in enumerate(lines) if i >= first_code and i not in set(late)]
    pre = [ln for ln in lines[:first_code] if not _IMPORT.match(ln)]
    repairs["imports_moved"] += len(late)
    return "\n".join(pre + head + ([""] if rest and rest[0].strip() else []) + rest)


_JAVA_TOP = re.compile(r"^\s*(?:(?:public|private|protected|abstract|final|static|sealed|non-sealed|strictfp)\s+)*"
                       r"(?:class|interface|enum|record)\s+\w|^\s*(?:import|package)\s|^\s*@\w|^\s*(?://|/\*|\*)")


def drop_java_outside_classes(code: str, repairs: Counter) -> str:
    """Java can't have anything outside a class: lines there are question text, output
    or labels that came along with the code (Student students[] = new Student[100];,
    O/P;, radius;). Dropping them can't break code that compiled before."""
    out, depth, removed, awaiting = [], 0, 0, False
    for line in code.split("\n"):
        bare = re.sub(r'"(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)\'|//.*$', "", line)
        top = depth == 0 and line.strip()
        if top and _JAVA_TOP.match(line) and "{" not in bare and not re.match(r"\s*(?:import|package|//|/\*|\*|@)", line):
            awaiting = True          # "class Car" with its { on a later line (or extends/implements first)
        elif top and not awaiting and not _JAVA_TOP.match(line):
            removed += 1                 # also a "}" that closes nothing, left by lines dropped above it
            continue
        out.append(line)
        if "{" in bare:
            awaiting = False
        depth = max(0, depth + bare.count("{") - bare.count("}"))
    if removed and any(_JAVA_TOP.match(ln) for ln in out):
        repairs["outside_class_removed"] += removed
        return "\n".join(out).strip("\n") + "\n"
    return code


# ------------------------------------------------------------------ Java copied out of a PDF
# Each repair below only touches text that can never be valid Java, so code that compiled
# before is never changed.
_CODELENS = re.compile(r"\bRun\s*\|\s*Debug\b\s*")                 # VS Code's links above main
_DIGIT_WORD = re.compile(r"^\s*\d+[A-Za-z]\w*\s*$")                 # 2025ITB085: a roll number in the header
_LONE_NUMBER = re.compile(r"^\s*\d{1,4}\s*$")                      # a line number (or output) on its own
# "9    public Student(…)" or "1.   class Car {": a line number (or the question's) before the code
_NUM_PREFIX = re.compile(r"^(\s*)\d{1,3}(?:[.):]\s+|\s{2,}|\.(?=[a-z_]\w*\s*[=.(]))(?=[A-Za-z_@/}{\"'])")
# "a       String model;", "ce   double area()": an IDE gutter (fold marks, breakpoints) read by OCR
_GUTTER = re.compile(r"^(\s*)(?!if\b|do\b)(?:[a-z0-9@]{1,2}|\d[A-Za-z]|[A-Za-z]\d)\s{4,}(?=(?:public|private|protected|static|final|abstract|class|"
                     r"int|double|float|long|short|byte|char|boolean|void|String|return|this\.|super|System\.|"
                     r"if|for|while|else|switch|try|catch|[A-Z]\w*(?:\[\])?\s+\w+)\b|[{}])")
# IntelliJ's grey parameter hints copied as text: new Student(name: "Anand", rollNumber: 101)
_INLAY_HINT = re.compile(r"(?<=[(,])(\s*)[A-Za-z_]\w*:\s")
_PRINTLN = re.compile(r"\b[Ss]ystem\s*\.\s*[Oo]ut\s*\.+\s*(?:printin|printlin|print1n|printIn|prinln|pritnln|printn|"
                      r"printline|printl|Println|PrintLn|printLn|PRINTLN)\s*\(")
_PRINT = re.compile(r"\b[Ss]ystem\s*\.\s*[Oo]ut\s*\.+\s*(Print|Printf)\s*\(")
_SYSTEM_LOWER = re.compile(r"\bsystem\s*\.\s*(?=out\b|in\b|err\b|exit\b)")
_SYSTEM_OUT = re.compile(r"\bSystem\s*\.\s*(?:Out|OUT)\b")
_LOWER_TYPES = {"string": "String", "scanner": "Scanner"}
_STR_LIT = re.compile(r'"(?:[^"\\\n]|\\.)*"')


def _code_part(line: str) -> str:
    """The line without string literals and // comments (where braces don't count)."""
    return re.sub(r"//.*$", "", _STR_LIT.sub('""', re.sub(r"'(?:[^'\\]|\\.)'", "' '", line)))


def _parens(text: str) -> int:
    bare = _code_part(text)
    return bare.count("(") - bare.count(")")


def _fix_line(line: str, repairs: Counter) -> str:
    new = _CODELENS.sub("", line)
    parts = re.split(r'("(?:[^"\\\n]|\\.)*")', new)
    new = "".join(p if i % 2 else _INLAY_HINT.sub(r"\1", p) for i, p in enumerate(parts))
    if new != line:
        repairs["ide_text_removed"] += 1
        line = new
    new = _PRINTLN.sub("System.out.println(", line)
    new = _PRINT.sub(lambda m: "System.out." + m.group(1).lower() + "(", new)
    new = _SYSTEM_OUT.sub("System.out", _SYSTEM_LOWER.sub("System.", new))
    if new != line:
        repairs["typo_fixed"] += 1
        line = new
    return line


def class_spans(lines: list[str]) -> list[tuple[str, int, int]]:
    """(name, first line, last line) of each top-level class, interface or enum."""
    spans, depth, start, name, opened = [], 0, None, None, False
    for i, line in enumerate(lines):
        bare = _code_part(line)
        if depth == 0 and start is None:
            m = re.search(r"\b(?:class|interface|enum|record)\s+([A-Za-z_]\w*)", bare)
            if m:
                start, name, opened = i, m.group(1), False
        depth += bare.count("{") - bare.count("}")
        if start is not None and "{" in bare:
            opened = True
        if start is not None and opened and depth <= 0:
            spans.append((name, start, i))
            start, depth = None, 0
    return spans


def _split_glued_keywords(code: str, declared: set, repairs: Counter) -> str:
    """The PDF lost the space after a keyword: `returnMath.PI * r * r`, `return2 * x`,
    `newCow("Gauri")`. Only names the code never declares are split."""
    # names the code declares: `int returnValue;`, `Cow newCow(` (a type, then the name)
    names = set(re.findall(r"\b[A-Za-z_][\w<>\[\],]*\s+([A-Za-z_]\w*)\s*[;=(,)]", _STR_LIT.sub('""', code)))

    def ret(m):
        glued = m.group(0)
        if glued in names:
            return glued
        repairs["space_restored"] += 1
        return "return " + glued[6:]

    def new(m):
        if m.group(1) not in declared or ("new" + m.group(1)) in names:
            return m.group(0)
        repairs["space_restored"] += 1
        return "new " + m.group(1)

    parts = re.split(r'("(?:[^"\\\n]|\\.)*")', code)
    for i in range(0, len(parts), 2):
        parts[i] = re.sub(r"\breturn(?:[A-Z]\w*|\d[\w.]*)", ret, parts[i])
        parts[i] = re.sub(r"\bnew([A-Z]\w*)(?=\s*[(\[])", new, parts[i])
    return "".join(parts)


def _uncapitalise_line_starts(code: str, declared: set, repairs: Counter) -> str:
    """Word capitalises the first word of a line: `speed = speed + amount;` becomes
    `Speed = speed + amount;`. A capitalised name that appears only at line starts, where its
    lower-case form is a name used elsewhere in the code, is put back."""
    starts = Counter(m.group(1) for m in re.finditer(r"(?m)^\s*([A-Z]\w*)\s*(?=[=.+\-\[(;])", code))
    if not starts:
        return code
    bare = _STR_LIT.sub('""', code)
    words = Counter(re.findall(r"\b[A-Za-z_]\w*\b", bare))
    for w, n in starts.items():
        low = w[0].lower() + w[1:]
        if w in declared or words[w] != n or not words[low] or w in ("System", "Math", "String", "Integer", "Double",
                                                                     "Arrays", "Character", "Thread", "Objects"):
            continue
        code, k = re.subn(rf"(?m)^(\s*){w}\b", rf"\g<1>{low}", code)
        repairs["auto_capital_fixed"] += k
    return code


_JAVA_START = re.compile(r"^\s*(?:(?:public|private|protected|abstract|final|static)\s+)*(?:class|interface|enum)\s+\w|^\s*import\s+[\w.]+")


# only words: `to int`, `calculate the method works`
_PROSE_TAIL = re.compile(r"^[A-Za-z][A-Za-z']*(?:[ ,]+[A-Za-z][A-Za-z']*)+[.,]?$")
_JAVA_WORDS = {"else", "do", "try", "finally", "return", "new", "throw", "case", "default", "int", "long",
               "short", "byte", "float", "double", "char", "boolean", "void", "var", "String", "public",
               "private", "protected", "static", "final", "abstract", "class", "interface", "enum", "import",
               "package", "extends", "implements", "throws", "synchronized"}


def repair_java(code: str, repairs: Counter) -> str:
    """Fix what copying Java out of a PDF or a screenshot does to it:
    - VS Code's "Run | Debug" above main, a roll number from the page header (2025ITB085)
    - line numbers: on their own line, or before the code ("9    public Student(…)")
    - stray lines from the page before: a "}" or the "* Model" lines of a lost /** comment
    - typos no program can mean: printin / print1n / printIn -> println, system.out, string args
    - the same class pasted twice (an earlier try left above the final one): the last is kept
    - closing braces lost at the end of the page"""
    if '"""' in code:
        return code
    lines, out = code.split("\n"), []
    in_comment, depth, prev_code = False, 0, ""
    open_parens = 0              # of a // comment that wrapped: `// System.out.println("x" +`
    for i, line in enumerate(lines):
        s = line.strip()
        if open_parens > 0 and s and not s.startswith("//"):
            # the rest of the commented-out statement, wrapped onto the next line
            out.append(line[:len(line) - len(line.lstrip())] + "// " + s)
            open_parens += _parens(s)
            repairs["wrapped_comment_joined"] += 1
            continue
        open_parens = 0
        if (out and out[-1].strip().startswith("//") and _PROSE_TAIL.match(s)
                and s.split()[0] not in _JAVA_WORDS):
            # the end of a sentence typed as a // comment, wrapped onto the next line
            out.append(line[:len(line) - len(line.lstrip())] + "// " + s)
            repairs["wrapped_comment_joined"] += 1
            continue
        if s.startswith("//"):
            body = s.lstrip("/").strip()
            if re.match(r"[\w.]+\s*(?:\(|=)", body) and not body.endswith((";", "{", "}")):
                open_parens = _parens(body)
        if in_comment:
            if "*/" not in s and depth == 0 and _JAVA_START.match(line) and not any("*/" in ln for ln in lines[i:]):
                # the comment's closing line was question text and got left out: close it before the code
                out.append("*/")
                repairs["comment_closed"] += 1
                in_comment = False
            else:
                out.append(line)
                if "*/" in s:
                    in_comment = False
                continue
        bare_open = _code_part(line)
        if "/*" in bare_open and "*/" not in bare_open[bare_open.index("/*"):]:
            in_comment = True
            out.append(line)
            continue
        if _DIGIT_WORD.match(line):
            repairs["header_text_removed"] += 1
            continue
        if _LONE_NUMBER.match(line) and (not prev_code or prev_code.endswith((";", "{", "}"))):
            repairs["line_number_removed"] += 1
            continue
        if (s.startswith("*") and not s.startswith("*=")) or s == "*/":
            if depth == 0 or not prev_code or prev_code.endswith((";", "{", "}")):
                repairs["stray_comment_removed"] += 1      # "* Model": the /** opening it is lost
                continue
        if s in (");", "));") and prev_code.endswith(";"):
            repairs["stray_text_removed"] += 1              # the end of a statement already complete
            continue
        if s in ("}", "};") and depth == 0:
            repairs["stray_brace_removed"] += 1             # closes nothing: from the page before
            continue
        m = _NUM_PREFIX.match(line)
        if m:
            line = m.group(1) + line[m.end():]
            repairs["line_number_removed"] += 1
        m = _GUTTER.match(line)
        if m:
            line = m.group(1) + line[m.end():]
            repairs["line_number_removed"] += 1
        line = _fix_line(line, repairs)
        if s and not line.strip():
            continue                                        # it held only "Run | Debug"
        out.append(line)
        bare = _code_part(line).strip()
        if bare:
            prev_code = bare
            depth = max(0, depth + bare.count("{") - bare.count("}"))
    code = "\n".join(out)

    declared = set(re.findall(r"\b(?:class|interface|enum)\s+(\w+)", code))
    for low, cap in _LOWER_TYPES.items():
        if low in declared:
            continue
        rx = re.compile(rf"\b{low}\b(?=\s*(?:\[\s*\]|\.\.\.|\s[A-Za-z_]|\())")
        fixed = []
        for line in code.split("\n"):
            parts = re.split(r'("(?:[^"\\\n]|\\.)*")', line)
            new = "".join(p if i % 2 else rx.sub(cap, p) for i, p in enumerate(parts))
            if new != line:
                repairs["typo_fixed"] += 1
            fixed.append(new)
        code = "\n".join(fixed)
    code = _uncapitalise_line_starts(code, declared, repairs)
    code = _split_glued_keywords(code, declared, repairs)
    if "This" not in declared:
        code, n = re.subn(r"\bThis\s*\.(?=\s*[a-z_])", "this.", code)
        if n:
            repairs["typo_fixed"] += n

    lines = code.split("\n")
    spans = class_spans(lines)
    names = [n for n, _, _ in spans]
    drop = set()
    for i, (n, a, b) in enumerate(spans):
        if names[i + 1:].count(n):
            drop.update(range(a, b + 1))
            repairs["duplicate_class_removed"] += 1
    if drop:
        lines = [ln for i, ln in enumerate(lines) if i not in drop]

    opens = sum(_code_part(ln).count("{") for ln in lines if not ln.strip().startswith(("*", "/*")))
    closes = sum(_code_part(ln).count("}") for ln in lines if not ln.strip().startswith(("*", "/*")))
    if 0 < opens - closes <= 3:
        while lines and not lines[-1].strip():
            lines.pop()
        lines += ["}"] * (opens - closes)
        repairs["closing_brace_added"] += opens - closes
    return "\n".join(lines)
