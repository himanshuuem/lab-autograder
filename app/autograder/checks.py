"""Requirement checks: tests for questions that say what a class must do rather than
what the program prints (each student invents their own data).

A check is a TestCase whose `check` field names one of the CHECKS below:
  run            the program compiles and runs without crashing
  out:lines:N    the program prints at least N lines
  src:<name>     a pattern in the source (e.g. an array of Student objects)
  py:<name>      a Python rule over source and output (e.g. prints the highest CGPA)
  java:<name>    behaviour, tested by AgCheck: a small class compiled next to the student's
                 code that finds their classes, fields and methods by meaning (increaseSpeed,
                 accelerate and speedUp all count) and calls them through reflection
"""
from __future__ import annotations

import re

CHECK_CLASS = "AgCheck"

# check id -> what it verifies, shown on the review page
CHECKS = {
    "run": "compiles and runs without crashing",
    "out:lines:3": "prints the details of at least three objects",
    "java:car_fields": "has fields for brand, model, colour and maximum speed",
    "java:student_fields": "has fields for name, roll number, department and CGPA",
    "py:highest_cgpa": "prints the student with the highest CGPA",
    "src:student_array": "keeps the students in an array or list of Student objects",
    "java:circle_radius": "has a radius field",
    "java:circle_area": "area for radius 3 is 28.27 (within 1.5%)",
    "java:circle_circumference": "circumference for radius 3 is 18.85 (within 1.5%)",
    "java:speed_private": "speed is a private field",
    "java:speed_max": "increasing the speed by 500 keeps it at 180 km/h or below",
    "java:speed_min": "decreasing the speed by 1000 keeps it at 0 km/h or above",
    "java:salary_private": "salary is a private field",
    "java:salary_set_get": "setting the salary to 5000 and retrieving it gives 5000",
    "java:salary_negative": "a negative salary (-100) is refused",
    "java:atm_private": "PIN and balance are private fields",
    "java:atm_deposit_negative": "depositing -100 leaves the balance unchanged",
    "java:atm_wrong_pin": "withdrawing with a wrong PIN leaves the balance unchanged",
    "java:atm_right_pin": "withdrawing 10 with the right PIN reduces the balance by 10",
}

# Object Oriented Programming lab, Assignment 1 (Car, Student, Circle, Car speed, Employee, ATM)
OOP_ASSIGNMENT_1 = {
    "1": ["run", "java:car_fields", "out:lines:3"],
    "2": ["run", "java:student_fields", "py:highest_cgpa", "src:student_array"],
    "3": ["run", "java:circle_radius", "java:circle_area", "java:circle_circumference"],
    "4": ["run", "java:speed_private", "java:speed_max", "java:speed_min"],
    "5": ["run", "java:salary_private", "java:salary_set_get", "java:salary_negative"],
    "6": ["run", "java:atm_private", "java:atm_deposit_negative", "java:atm_wrong_pin", "java:atm_right_pin"],
}

PACKS = {"oop-assignment-1": OOP_ASSIGNMENT_1}

# the other lab sheets (packs.py): their questions come with the pack
from . import packs as _packs  # noqa: E402

CHECKS.update({cid: desc for cid, (desc, _) in _packs.CHECKS.items()})
SPECS = {cid: how for cid, (_, how) in _packs.CHECKS.items() if how}
for _name, _questions in _packs.PACKS.items():
    PACKS[_name] = {label: ids for label, _, _, ids in _questions}


def _set_questions(db, assignment, questions) -> None:
    """Make the assignment's questions the sheet's: titles and statements updated, questions
    the sheet doesn't have removed unless a TA added tests to them by hand."""
    from .models import Question
    by_label = {q.label: q for q in assignment.questions}
    wanted = [label for label, *_ in questions]
    for q in list(assignment.questions):
        if q.label not in wanted and not any(t.source == "manual" for t in q.tests):
            assignment.questions.remove(q)
    for pos, (label, title, statement, _) in enumerate(questions):
        q = by_label.get(label)
        if q is None:
            q = Question(label=label, weight=1.0)
            assignment.questions.append(q)
        q.title, q.statement, q.position = title[:300], statement, pos
    extra = [q for q in assignment.questions if q.label not in wanted]
    for i, q in enumerate(sorted(extra, key=lambda q: q.position)):
        q.position = len(questions) + i          # a TA's own questions come after the sheet's
    db.flush()


def install(db, assignment, pack: str) -> int:
    """Replace the assignment's requirement checks with the pack's, question by question.
    A pack for a whole sheet also sets the questions. Input/output tests (from the PDF or
    added by hand) are kept."""
    from .models import TestCase
    plan = PACKS[pack]
    if pack in _packs.PACKS:
        _set_questions(db, assignment, _packs.PACKS[pack])
        assignment.tests_imported = True        # don't let grading re-read the sheet over these questions
    n = 0
    for q in assignment.questions:
        ids = plan.get(q.label)
        if not ids:
            continue
        q.tests[:] = [t for t in q.tests if not t.rule]
        start = len(q.tests)
        for i, cid in enumerate(ids):
            q.tests.append(TestCase(stdin="", expected=CHECKS[cid], rule=cid, source="check",
                                    hidden=False, weight=1.0, position=start + i))
            n += 1
    db.flush()
    return n


SOURCE_RULES = {
    "student_array": re.compile(r"\bStudent\s*\[\s*\]|\bnew\s+Student\s*\[|(?:List|ArrayList|Vector)\s*<\s*Student\s*>",
                                re.I),
}
SOURCE_RULES.update({name: re.compile(rx) for name, rx in _packs.SOURCE_RULES.items()})
OUTPUT_RULES = {name: [re.compile(rx, re.I) for rx in rxs] for name, rxs in _packs.OUTPUT_RULES.items()}


def class_names(code: str) -> list[str]:
    """Top-level and nested class names declared in the student's code."""
    clean = re.sub(r"//[^\n]*|/\*.*?\*/|\"(?:[^\"\\]|\\.)*\"", " ", code or "", flags=re.S)
    return list(dict.fromkeys(re.findall(r"\b(?:class|enum|record)\s+([A-Za-z_]\w*)", clean)))


def needs_input(stderr: str) -> bool:
    return "NoSuchElementException" in (stderr or "") or "InputMismatchException" in (stderr or "")


# Compile errors the lab sheets ask students to show ("predict whether it compiles", "attempt to
# access the private salary and observe the result", "place a statement before super()"…).
DEMO_ERRORS = re.compile(
    r"reference to \w+ is ambiguous|has private access in|call to (?:super|this) must be first statement"
    r"|is abstract; cannot be instantiated|possible lossy conversion from|no suitable constructor found for \w+\((?:float|char)\)")
_ERROR_LINE = re.compile(r"^[\w$]+\.java:(\d+): error: (.*)$", re.M)


def demo_error_lines(compile_output: str) -> set[int] | None:
    """The lines to comment out when every compile error is one the sheet asks for, else None."""
    errors = _ERROR_LINE.findall(compile_output or "")
    if not errors or len(errors) > 4 or not all(DEMO_ERRORS.search(msg) for _, msg in errors):
        return None
    return {int(n) for n, _ in errors}


def comment_out(code: str, lines: set[int]) -> str:
    out = code.split("\n")
    for n in lines:
        if 0 < n <= len(out):
            out[n - 1] = "// [autograder: the compile error asked for] " + out[n - 1].lstrip()
    return "\n".join(out)


def check_run(status: str, stderr: str) -> tuple[bool, str]:
    if status == "OK":
        return True, "ran and finished normally"
    if status == "RUNTIME_ERROR" and needs_input(stderr):
        return True, "ran; it waits for keyboard input, which this check doesn't give"
    return False, {"TLE": "took too long (endless loop?)", "RUNTIME_ERROR": "crashed while running",
                   "MLE": "used too much memory", "OUTPUT_LIMIT": "printed far too much"}.get(status, status)


def check_lines(stdout: str, n: int) -> tuple[bool, str]:
    lines = [ln for ln in (stdout or "").splitlines() if ln.strip()]
    return (len(lines) >= n), f"printed {len(lines)} line(s)"


def _no_comments(code: str) -> str:
    return re.sub(r"//[^\n]*|/\*.*?\*/", " ", code or "", flags=re.S)


def check_source(name: str, code: str) -> tuple[bool, str]:
    ok = bool(SOURCE_RULES[name].search(_no_comments(code)))
    return ok, "found in the code" if ok else "not found in the code"


def check_output(name: str, stdout: str) -> tuple[bool, str]:
    """Every pattern of the rule, in order, in what the program printed."""
    pos, text = 0, stdout or ""
    for rx in OUTPUT_RULES[name]:
        m = rx.search(text, pos)
        if not m:
            return False, f"the output doesn't show {rx.pattern.split('|')[0].replace(chr(92), '')!r}" + \
                ("" if pos == 0 else " after the earlier part")
        pos = m.end()
    return True, "found in the output"


def check_discount(stdout: str, rate: float = 0.15) -> tuple[bool, str]:
    """Some price and that price less the discount are both printed."""
    nums = [float(x) for x in re.findall(r"(?<![\w.])\d+(?:\.\d+)?", stdout or "")]
    for a in nums:
        for b in nums:
            if a > 0 and abs(b - a * (1 - rate)) <= max(0.01, a * 0.001):
                return True, f"{_fmt(a)} and {_fmt(b)} (15% off) are both printed"
    return False, "no price and its 15%-off price were both printed"


def _fmt(x: float) -> str:
    return str(int(x)) if x == int(x) else str(x)


def _num(s: str) -> float:
    return float(s)


# What grading types for a program that reads the keyboard: 3 students, every field of the
# first one 7, of the second 9, of the third 8 (then 6s for anything else it asks), so the
# student with the highest CGPA is the "9" one whatever order the fields are read in.
KEYBOARD_INPUT = "3\n" + "7\n" * 4 + "9\n" * 4 + "8\n" * 4 + "6\n" * 60
KEYBOARD_NOTE = "3 students whose values are all 7, all 9 and all 8"


def _split_args(args: str) -> list[str]:
    """`"a, b", 3, f(1, 2)` -> ['"a, b"', '3', 'f(1, 2)']: commas inside strings and calls don't split."""
    parts, cur, depth, quote = [], "", 0, ""
    for ch in args:
        if quote:
            cur += ch
            if ch == quote:
                quote = ""
        elif ch in "\"'":
            quote = ch
            cur += ch
        elif ch in "([{":
            depth += 1
            cur += ch
        elif ch in ")]}":
            depth -= 1
            cur += ch
        elif ch == "," and depth == 0:
            parts.append(cur.strip())
            cur = ""
        else:
            cur += ch
    parts.append(cur.strip())
    return parts


def _student_class(code: str) -> str:
    """The class that holds the students, as a regex: Student, or whatever the code calls it
    (`student`, `Students`, `StudentInfo`): a class declaring a cgpa-like field."""
    names = {"Student"}
    for m in re.finditer(r"\bclass\s+([A-Za-z_]\w*)\s*[^{]*\{", code):
        body = code[m.end():m.end() + 2000]
        if re.search(r"\b(?:double|float|Double|Float|int)\s+\w*gpa\w*\s*[;,=]", body, re.I) or re.search(r"stud", m.group(1), re.I):
            names.add(m.group(1))
    return "(?:" + "|".join(sorted(map(re.escape, names))) + ")"


def _cgpa_slot(code: str) -> tuple[int | None, int]:
    """Which argument of `Student(...)` is the CGPA, from the constructor's own parameters:
    the one named like cgpa/cg/gpa, else the only double/float one."""
    for params in re.findall(r"\b" + _student_class(code) + r"\s*\(([^()]*)\)\s*(?:throws\s+[\w.,\s]+)?\{", code):
        names = [p.split() for p in _split_args(params) if p.strip()]
        if not names or any(len(n) < 2 for n in names):
            continue
        by_name = [i for i, n in enumerate(names) if re.search(r"c?gpa|^cg", n[-1], re.I)]
        by_type = [i for i, n in enumerate(names) if n[-2] in ("double", "float", "Double", "Float")]
        pick = by_name or (by_type if len(by_type) == 1 else [])
        if len(pick) == 1:
            return pick[0], len(names)
    return None, 0


def check_highest_cgpa(code: str, stdout: str, typed: bool = False) -> tuple[bool, str]:
    """The CGPA values are the decimal arguments in `new Student(...)` calls (or assigned
    to a cgpa field); the program must print the largest of them. When the students were
    typed in (KEYBOARD_INPUT), the last line with a number must show the 9 student."""
    values = []
    slot, n_params = _cgpa_slot(code or "")
    for args in re.findall(r"new\s+" + _student_class(code or "") + r"\s*\(([^;]*?)\)\s*[;,)]", code or "", flags=re.S):
        parts = _split_args(args)
        if slot is not None and len(parts) == n_params:
            # the argument in the constructor's CGPA position, whole numbers too (9 is a CGPA)
            m = re.fullmatch(r"(\d+(?:\.\d+)?)[fFdD]?", parts[slot])     # 8.82f is a float literal
            if m and 0 < _num(m.group(1)) <= 10:
                values.append(m.group(1))
            continue
        nums = [n for n in re.findall(r"(?<![\w.])(\d+\.\d+|\d+)[fFdD]?(?![\w.])", args)]
        dec = [n for n in nums if "." in n and 0 <= _num(n) <= 10]
        if dec:
            values.append(dec[-1])
    for n in re.findall(r"\b\w*cgpa\w*\s*=\s*(\d+(?:\.\d+)?)[fFdD]?\s*;", code or "", flags=re.I):
        if 0 < _num(n) <= 10:          # `cgpa = 0;` is a default before the real value is read, not a CGPA
            values.append(n)
    if not values and typed:
        last = next((ln for ln in reversed((stdout or "").splitlines()) if re.search(r"\d", ln)), "")
        ok = bool(re.search(r"(?<![\d.])9(?:\.0+)?(?![\d.])", last))
        return ok, ("the last line shows the student with CGPA 9" if ok
                    else f"the last line doesn't show the student with CGPA 9: {last.strip()[:80]!r}")
    if not values:
        return False, "couldn't find the CGPA values in the code (read from input?): check by hand"
    best = max(values, key=_num)
    printed = [_num(x) for x in re.findall(r"(?<![\d.])\d+(?:\.\d+)?(?!\d)", stdout or "")]
    ok = any(abs(x - _num(best)) < 1e-9 for x in printed)
    return ok, f"highest CGPA in the code is {best}; " + ("printed" if ok else "not found in the output")


_OCR_LOOKALIKE = str.maketrans({"@": "0", "O": "0", "o": "0", "Q": "0", "D": "0", "l": "1", "I": "1", "|": "1",
                                "S": "5", "B": "8", "Z": "2"})


def _norm(text: str, ocr: bool) -> str:
    t = re.sub(r"\s+", " ", (text or "").strip()).lower() if not ocr else re.sub(r"\s+", " ", (text or "").strip())
    return t.translate(_OCR_LOOKALIKE).lower() if ocr else t


# a line of code in a screenshot of the editor, not of the program's output
_CODE_LINE = re.compile(r"[;{]\s*$|^\s*}|\b(?:public|private|static|void|class|import|System\.out|return)\b|^\s*(?:if|for|while)\s*\(")


def _clean_lines(text: str) -> list[tuple[str, list[float]]]:
    """The lines of a screenshot worth comparing: no terminal prompts, window titles or
    OCR noise ("ei.) Crea ee eesk=400"), each as (its letters, its numbers)."""
    from docextract.cleanup import is_terminal_noise
    out = []
    for ln in (text or "").splitlines():
        t = ln.strip()
        if not t or is_terminal_noise(t) or re.search(r"\w+@[\w.-]+.*[$#%]|[~/\\]\S*[$>]|\bjavac?\b|\bnano\b", t):
            continue
        letters = sum(c.isalnum() for c in t)
        if letters < 4 or letters < 0.6 * len(t.replace(" ", "")):
            continue
        # a glyph or two at the window's edge, far from the text: "Creating object      4"
        t = re.sub(r"^\S{1,2}\s{3,}|\s{3,}\S{1,2}$", "", t)
        nums = [float(n) for tok in re.findall(r"\S*\d\S*", t)       # 18@ is 180; words keep their letters
                for n in re.findall(r"\d+(?:\.\d+)?", tok.translate(_OCR_LOOKALIKE))]
        out.append((re.sub(r"[^a-z]", "", t.lower()), nums))
    return out


def _screenshot_differs(shown: str, prints: str) -> bool:
    """Line by line: a screenshot is a different program's output only when it shows at
    least two clean lines the program never prints, and most of its lines are like that.
    A cropped screenshot, a few misread lines, or a picture of the code are not."""
    import difflib
    if sum(bool(_CODE_LINE.search(ln)) for ln in shown.splitlines()) >= 2:
        return False                                    # the editor, not the output
    lines, real = _clean_lines(shown), [x for x in _clean_lines(prints) if x[0] or x[1]]
    if len(lines) < 2 or not real:
        return False

    def same_numbers(a, b):     # 78.54 is not 0.785, whatever the letters around it
        return all(any(abs(x - y) <= 0.01 * max(abs(x), abs(y)) + 1e-9 for y in b) for x in a)

    def found(ln):
        words, nums = ln
        return any((words in w or w in words if words and w else words == w
                    or difflib.SequenceMatcher(None, words, w).ratio() >= 0.75)
                   and same_numbers(nums, ns) for w, ns in real)
    missing = sum(not found(ln) for ln in lines)
    return missing >= 2 and missing > len(lines) / 2


def shown_output_differs(shown: str | None, prints: str, from_image: bool) -> bool:
    """Is the output the student showed clearly not what their code prints? A cropped
    screenshot (the start of the output) and OCR misreadings (18@ for 180) are not."""
    if not shown or not (prints or "").strip():
        return False
    if from_image:
        return _screenshot_differs(shown, prints)
    import difflib
    a, b = _norm(shown, from_image), _norm(prints, from_image)
    if not a or a in b:
        return False
    if not from_image:              # typed output: the numbers must be the program's own, in order
        na, nb = re.findall(r"-?\d+(?:\.\d+)?", a), re.findall(r"-?\d+(?:\.\d+)?", b)
        if na and na != nb[:len(na)]:
            return True
    # compare with the part of the real output the screenshot would cover
    part = b[:max(len(a) + 10, int(len(a) * 1.2))]
    ratio = max(difflib.SequenceMatcher(None, a, part).ratio(), difflib.SequenceMatcher(None, a, b).ratio())
    return ratio < (0.75 if from_image else 0.9)


def harness_tests(check_ids: list[str], code: str) -> list[str]:
    """stdin for each AgCheck run: the check (its spec, for the generic ones), then the
    student's class names."""
    names = ",".join(n for n in class_names(code) if n != CHECK_CLASS)
    return [f"{SPECS.get(cid) or cid.split(':', 1)[1]}\n{names}\n" for cid in check_ids]


def is_harness_check(cid: str) -> bool:
    return cid.startswith("java:") or cid in SPECS


def parse_harness(stdout: str) -> tuple[bool, str]:
    last = next((ln for ln in reversed((stdout or "").splitlines()) if ln.startswith(("PASS", "FAIL"))), "")
    if not last:
        return False, "the check could not run"
    ok = last.startswith("PASS")
    msg = last[4:].lstrip(": ").strip()
    return ok, msg or ("passed" if ok else "failed")


# ------------------------------------------------------------------ the Java side
JAVA_HARNESS = r'''
class AgCheck {
    static java.util.List<Class<?>> classes = new java.util.ArrayList<>();
    static java.io.PrintStream REAL = System.out;
    static java.io.ByteArrayOutputStream captured = new java.io.ByteArrayOutputStream();

    public static void main(String[] args) {
        java.util.Scanner in = new java.util.Scanner(System.in);
        String id = in.hasNextLine() ? in.nextLine().replaceAll("^ +|\\r$", "") : "";   // a spec may end in an empty field
        String names = in.hasNextLine() ? in.nextLine().trim() : "";
        for (String n : names.split(",")) {
            try { if (!n.isEmpty()) addWithNested(Class.forName(n)); } catch (Throwable t) { }
        }
        feed("");                                               // student code never waits for a keyboard
        System.setOut(new java.io.PrintStream(captured));     // the student's own prints are not the result
        String r;
        try { r = run(id); }
        catch (Fail f) { r = "FAIL: " + f.getMessage(); }
        catch (Throwable t) { r = "FAIL: " + t.getClass().getSimpleName() + (t.getMessage() == null ? "" : ": " + t.getMessage()); }
        System.setOut(REAL);
        System.out.println(r.replace('\n', ' '));
        System.exit(0);
    }

    static class Fail extends RuntimeException { Fail(String m) { super(m); } }

    static void addWithNested(Class<?> c) {
        if (classes.contains(c)) return;
        classes.add(c);
        for (Class<?> k : c.getDeclaredClasses()) addWithNested(k);
    }

    /** What the student's code will read from the keyboard next. */
    static void feed(String s) { System.setIn(new java.io.ByteArrayInputStream(s.getBytes())); }

    static String run(String id) throws Exception {
        if (id.indexOf('\t') >= 0) return generic(id.split("\t", -1));
        switch (id) {
            case "car_fields": return fields(new String[]{"brand", "model", "colou?r", "speed"},
                                             new String[]{"brand", "model", "colour", "maximum speed"});
            case "student_fields": return fields(new String[]{"name", "roll", "dep|dept|branch|stream|department", "cgpa|gpa|cg|grade"},
                                                 new String[]{"name", "roll number", "department", "CGPA"});
            case "circle_radius": classWith(RADIUS); return "PASS";
            case "circle_area": return circle(java.lang.Math.PI * 9, "area");
            case "circle_circumference": return circle(2 * java.lang.Math.PI * 3, "circum|perim");
            case "speed_private": return isPrivate(speedField(classWith(SPEED)));
            case "speed_max": return speed(true);
            case "speed_min": return speed(false);
            case "salary_private": return isPrivate(field(classWith("sal"), "sal"));
            case "salary_set_get": return salary(false);
            case "salary_negative": return salary(true);
            case "atm_private": { Class<?> c = classWith("pin", "bal|amount|money");
                                  String a = isPrivate(field(c, "pin")), b = isPrivate(field(c, "bal|amount|money"));
                                  return a.startsWith("FAIL") ? a : b; }
            case "atm_deposit_negative": return atmDeposit();
            case "atm_wrong_pin": return atmWithdraw(false);
            case "atm_right_pin": return atmWithdraw(true);
        }
        return "FAIL: unknown check " + id;
    }

    static final String SPEED = "speed";
    static final String RADIUS = "^rad|radius|^r$|^r\\d$";
    static final String INC = "inc|acc|speed.?up|raise|faster|boost|(^|_)in_|add|edd|plus|more|^up";
    static final String DEC = "dec|brake|slow|reduc|down|(^|_)de_|sub|zub|minus|less";

    // ---------------------------------------------------------------- finding things by meaning
    static java.util.List<java.lang.reflect.Field> allFields(Class<?> c) {
        java.util.List<java.lang.reflect.Field> out = new java.util.ArrayList<>();
        for (Class<?> k = c; k != null && k != Object.class; k = k.getSuperclass())
            for (java.lang.reflect.Field f : k.getDeclaredFields())
                if (!java.lang.reflect.Modifier.isStatic(f.getModifiers()) && !f.isSynthetic()) out.add(f);
        return out;
    }

    static boolean matches(String name, String regex) {
        return java.util.regex.Pattern.compile(regex, java.util.regex.Pattern.CASE_INSENSITIVE).matcher(name).find();
    }

    static java.lang.reflect.Field field(Class<?> c, String regex) {
        for (java.lang.reflect.Field f : allFields(c)) if (matches(f.getName(), regex)) { f.setAccessible(true); return f; }
        throw new Fail("no field like '" + regex.split("\\|")[0] + "' in class " + c.getSimpleName());
    }

    static java.lang.reflect.Field speedField(Class<?> c) {
        for (java.lang.reflect.Field f : allFields(c))
            if (matches(f.getName(), SPEED) && !matches(f.getName(), "max|limit|top|min") && isNumeric(f.getType())) {
                f.setAccessible(true); return f;
            }
        throw new Fail("no current-speed field in class " + c.getSimpleName());
    }

    static Class<?> classWith(String... regexes) {
        Class<?> best = null; int bestScore = -1;
        for (Class<?> c : classes) {
            int score = 0;
            for (String r : regexes) for (java.lang.reflect.Field f : allFields(c)) if (matches(f.getName(), r)) { score++; break; }
            if (score == regexes.length && (c.isInterface() == false) && score > bestScore) { best = c; bestScore = score; }
        }
        if (best == null) throw new Fail("no class with a field like '" + regexes[0].split("\\|")[0] + "'");
        return best;
    }

    static java.util.List<java.lang.reflect.Method> methods(Class<?> c, String regex, String not) {
        java.util.List<java.lang.reflect.Method> out = new java.util.ArrayList<>();
        for (Class<?> k = c; k != null && k != Object.class; k = k.getSuperclass())
            for (java.lang.reflect.Method m : k.getDeclaredMethods())
                if (!java.lang.reflect.Modifier.isStatic(m.getModifiers()) && matches(m.getName(), regex)
                        && (not == null || !matches(m.getName(), not))) { m.setAccessible(true); out.add(m); }
        return out;
    }

    static boolean isNumeric(Class<?> t) {
        return t == int.class || t == long.class || t == double.class || t == float.class || t == short.class
            || t == Integer.class || t == Long.class || t == Double.class || t == Float.class || t == Short.class;
    }

    static Object cast(double v, Class<?> t) {
        if (t == int.class || t == Integer.class) return (int) v;
        if (t == long.class || t == Long.class) return (long) v;
        if (t == float.class || t == Float.class) return (float) v;
        if (t == short.class || t == Short.class) return (short) v;
        return v;
    }

    static Object arg(Class<?> t, double v) {
        if (isNumeric(t)) return cast(v, t);
        if (t == String.class) return "Test";
        if (t == boolean.class || t == Boolean.class) return true;
        if (t == char.class || t == Character.class) return 'A';
        return null;
    }

    /** An object of c, built with every numeric constructor argument = v. */
    static Object make(Class<?> c, double v) throws Exception {
        java.lang.reflect.Constructor<?>[] cs = c.getDeclaredConstructors();
        java.util.Arrays.sort(cs, (a, b) -> numericParams(b) - numericParams(a));
        Throwable last = null;
        for (java.lang.reflect.Constructor<?> k : cs) {
            k.setAccessible(true);
            Object[] a = new Object[k.getParameterCount()];
            Class<?>[] ts = k.getParameterTypes();
            for (int i = 0; i < a.length; i++) a[i] = arg(ts[i], v);
            try { return k.newInstance(a); } catch (Throwable t) { last = t; }
        }
        throw new Fail("could not create a " + c.getSimpleName() + (last == null ? "" : " (" + cause(last) + ")"));
    }

    static int numericParams(java.lang.reflect.Constructor<?> k) {
        int n = 0; for (Class<?> t : k.getParameterTypes()) if (isNumeric(t)) n++; return n;
    }

    static String cause(Throwable t) {
        while (t.getCause() != null) t = t.getCause();
        return t.getClass().getSimpleName() + (t.getMessage() == null ? "" : ": " + t.getMessage());
    }

    static double get(Object o, java.lang.reflect.Field f) throws Exception { return ((java.lang.Number) f.get(o)).doubleValue(); }
    static void set(Object o, java.lang.reflect.Field f, double v) throws Exception { f.set(o, cast(v, f.getType())); }

    /** Call m; a method that prints its answer instead of returning it is read from what it printed. */
    static Double call(java.lang.reflect.Method m, Object o, Object... a) throws Exception {
        captured.reset();
        Object r;
        try { r = m.invoke(o, a); }
        catch (java.lang.reflect.InvocationTargetException e) { return null; }    // refused by throwing
        if (r instanceof java.lang.Number) return ((java.lang.Number) r).doubleValue();
        java.util.regex.Matcher mm = java.util.regex.Pattern.compile("-?\\d+(?:\\.\\d+)?").matcher(captured.toString());
        Double last = null; while (mm.find()) last = Double.parseDouble(mm.group());
        return last;
    }

    static void invoke(java.lang.reflect.Method m, Object o, Object... a) throws Exception {
        try { m.invoke(o, a); } catch (java.lang.reflect.InvocationTargetException e) { /* refused by throwing */ }
    }

    static boolean numericArgs(java.lang.reflect.Method m, int n) {
        if (m.getParameterCount() != n) return false;
        for (Class<?> t : m.getParameterTypes()) if (!isNumeric(t)) return false;
        return true;
    }

    // ---------------------------------------------------------------- the checks
    static String fields(String[] regexes, String[] names) {
        Class<?> best = null; java.util.List<String> bestMissing = null;
        for (Class<?> c : classes) {
            java.util.List<String> missing = new java.util.ArrayList<>();
            for (int i = 0; i < regexes.length; i++) {
                boolean found = false;
                for (java.lang.reflect.Field f : allFields(c)) if (matches(f.getName(), regexes[i])) { found = true; break; }
                if (!found) missing.add(names[i]);
            }
            if (bestMissing == null || missing.size() < bestMissing.size()) { best = c; bestMissing = missing; }
        }
        if (best == null) return "FAIL: no classes found";
        return bestMissing.isEmpty() ? "PASS: class " + best.getSimpleName()
                                     : "FAIL: class " + best.getSimpleName() + " has no field for " + String.join(", ", bestMissing);
    }

    static String isPrivate(java.lang.reflect.Field f) {
        return java.lang.reflect.Modifier.isPrivate(f.getModifiers()) ? "PASS: " + f.getName() + " is private"
                                                                     : "FAIL: " + f.getName() + " is not private";
    }

    static String circle(double want, String what) throws Exception {
        Class<?> c = classWith(RADIUS);
        java.lang.reflect.Field rf = field(c, RADIUS);
        Object o = make(c, 3);
        if (java.lang.Math.abs(get(o, rf) - 3) > 1e-9) set(o, rf, 3);
        Double got = null;
        for (java.lang.reflect.Method m : methods(c, what, null))
            if (m.getParameterCount() == 0) { got = call(m, o); if (got != null) break; }
        if (got == null) for (java.lang.reflect.Method m : methods(c, what, null))
            if (numericArgs(m, 1)) { got = call(m, o, cast(3, m.getParameterTypes()[0])); if (got != null) break; }
        if (got == null) for (java.lang.reflect.Field f : allFields(c))
            if (matches(f.getName(), what) && isNumeric(f.getType())) { f.setAccessible(true); got = get(o, f); }
        if (got == null) return "FAIL: no method that gives the " + (what.startsWith("area") ? "area" : "circumference");
        boolean ok = java.lang.Math.abs(got - want) <= 0.015 * want;
        return (ok ? "PASS: " : "FAIL: ") + "radius 3 gave " + round(got) + " (expected " + round(want) + ")";
    }

    static String round(double v) { return String.valueOf(java.lang.Math.round(v * 100) / 100.0); }

    static String speed(boolean up) throws Exception {
        Class<?> c = classWith(SPEED);
        java.lang.reflect.Field sf = speedField(c);
        Object o = make(c, 0);
        java.util.List<java.lang.reflect.Method> inc = methods(c, INC, DEC);
        java.util.List<java.lang.reflect.Method> dec = methods(c, DEC, INC);
        java.util.List<java.lang.reflect.Method> setter = methods(c, "^set.*speed|^change.*speed|^update.*speed", null);
        if (setter.isEmpty())        // e.g. Speed(int s): one method that sets the speed
            for (java.lang.reflect.Method m : methods(c, "speed", "get|show|display|print|max|" + INC + "|" + DEC))
                if (numericArgs(m, 1)) setter.add(m);
        if (!up) step(o, inc.isEmpty() ? setter : inc, 100, 5);
        java.util.List<java.lang.reflect.Method> use = up ? (inc.isEmpty() ? setter : inc) : (dec.isEmpty() ? setter : dec);
        if (use.isEmpty()) return "FAIL: no method to " + (up ? "increase" : "decrease") + " the speed";
        boolean viaSetter = up ? inc.isEmpty() : dec.isEmpty();
        double amount = up ? 500 : (viaSetter ? -1000 : 1000);
        if (!step(o, use, amount, 60)) return "FAIL: the " + (up ? "increase" : "decrease") + " method takes arguments it can't be given";
        double v = get(o, sf);
        boolean ok = up ? v <= 180 + 1e-9 && v >= 0 : v >= -1e-9 && v <= 180;
        return (ok ? "PASS: " : "FAIL: ") + "speed became " + round(v) + " after " + (up ? "increasing by 500" : "decreasing by 1000");
    }

    /** Use a speed method: with the amount if it takes a number, else call it `times` times. */
    static boolean step(Object o, java.util.List<java.lang.reflect.Method> ms, double amount, int times) throws Exception {
        for (java.lang.reflect.Method m : ms)
            if (numericArgs(m, 1)) { invoke(m, o, cast(amount, m.getParameterTypes()[0])); return true; }
        for (java.lang.reflect.Method m : ms)
            if (m.getParameterCount() == 0) { for (int i = 0; i < times; i++) invoke(m, o); return true; }
        return false;
    }

    static String salary(boolean negative) throws Exception {
        Class<?> c = classWith("sal");
        java.lang.reflect.Field sf = field(c, "sal");
        Object o = make(c, 1000);
        java.lang.reflect.Method setter = null, getter = null;
        for (java.lang.reflect.Method m : methods(c, "set.*sal|sal.*set|update.*sal|change.*sal|^setSal|^sal", "get"))
            if (numericArgs(m, 1)) { setter = m; break; }
        for (java.lang.reflect.Method m : methods(c, "get.*sal|^sal|retriev|show.*sal|display.*sal", "set"))
            if (m.getParameterCount() == 0 || numericArgs(m, 1)) { getter = m; break; }
        if (setter == null) return "FAIL: no method to set the salary";
        invoke(setter, o, cast(5000, setter.getParameterTypes()[0]));
        if (!negative) {
            if (getter == null) return "FAIL: no method to retrieve the salary";
            Double got = getter.getParameterCount() == 0 ? call(getter, o)
                                                         : call(getter, o, cast(0, getter.getParameterTypes()[0]));
            if (got == null) return "FAIL: retrieving the salary gave nothing";
            return (java.lang.Math.abs(got - 5000) < 0.01 ? "PASS: " : "FAIL: ") + "set 5000, got back " + round(got);
        }
        invoke(setter, o, cast(-100, setter.getParameterTypes()[0]));
        double v = get(o, sf);
        return (v >= 0 ? "PASS: " : "FAIL: ") + "after setting -100 the salary is " + round(v);
    }

    // ---------------------------------------------------------------- ATM
    static java.lang.reflect.Field pinF, balF;
    static final Object SCANNER = new Object();      // "give this parameter a Scanner over the input"

    static Object atm() throws Exception {
        Class<?> c = classWith("pin", "bal|amount|money");
        pinF = field(c, "pin"); balF = field(c, "bal|amount|money");
        Object o = make(c, 1234);
        if (get(o, balF) < 1000) set(o, balF, 1000);
        return o;
    }

    static String pinText(Object o, boolean right) throws Exception {
        Object p = pinF.get(o);
        if (p instanceof java.lang.Number) {
            long v = ((java.lang.Number) p).longValue();
            return String.valueOf(right ? v : v + 1);
        }
        return right ? String.valueOf(p) : p + "9";
    }

    static Object pinArg(Object o, boolean right, Class<?> t) throws Exception {
        String s = pinText(o, right);
        return t == String.class ? s : cast(Double.parseDouble(s), t);
    }

    static boolean pinLike(Class<?> t) { return t == pinF.getType() || t == String.class || (isNumeric(t) && isNumeric(pinF.getType())); }

    static class Call { Object[] args; String input; boolean pin; Call(Object[] a, String i, boolean p) { args = a; input = i; pin = p; } }

    static String amt(double v) { return v == java.lang.Math.rint(v) ? String.valueOf((long) v) : String.valueOf(v); }

    /** Every way to call an (amount[, pin]) method: as arguments, or typed at the keyboard. */
    static java.util.List<Call> callsFor(java.lang.reflect.Method m, Object o, double amount, boolean rightPin) throws Exception {
        java.util.List<Call> out = new java.util.ArrayList<>();
        Class<?>[] ts = m.getParameterTypes();
        String a = amt(amount), p = pinText(o, rightPin);
        boolean keyboard = ts.length == 0 || (ts.length == 1 && ts[0] == java.util.Scanner.class);
        if (keyboard) {
            Object[] args = ts.length == 0 ? new Object[0] : new Object[]{SCANNER};
            out.add(new Call(args, a + "\n", false));
            out.add(new Call(args, p + "\n" + a + "\n", true));
            out.add(new Call(args, a + "\n" + p + "\n", true));
        }
        if (ts.length == 1 && isNumeric(ts[0])) {
            out.add(new Call(new Object[]{cast(amount, ts[0])}, "", false));
            out.add(new Call(new Object[]{cast(amount, ts[0])}, p + "\n", true));     // asks for the PIN itself
        }
        if (ts.length == 2) for (int pi = 0; pi < 2; pi++) {
            int ai = 1 - pi;
            if (isNumeric(ts[ai]) && pinLike(ts[pi])) {
                Object[] args = new Object[2];
                args[ai] = cast(amount, ts[ai]); args[pi] = pinArg(o, rightPin, ts[pi]);
                out.add(new Call(args, "", true));
            }
        }
        return out;
    }

    /** Type the call's input, make a fresh ATM (its Scanner reads that input), and call m. */
    static Object[] attempt(java.lang.reflect.Method m, Call call, java.util.List<java.lang.reflect.Method> before,
                            boolean rightPin) throws Exception {
        feed(call.input);
        Object o = atm();
        double b = get(o, balF);
        for (java.lang.reflect.Method v : before) invoke(v, o, pinArg(o, rightPin, v.getParameterTypes()[0]));
        Object[] args = call.args.clone();
        for (int i = 0; i < args.length; i++)
            if (args[i] == SCANNER) args[i] = new java.util.Scanner(new java.io.ByteArrayInputStream(call.input.getBytes()));
        invoke(m, o, args);
        return new Object[]{b, get(o, balF)};
    }

    static java.util.List<java.lang.reflect.Method> verifiers(Class<?> c) {
        java.util.List<java.lang.reflect.Method> out = new java.util.ArrayList<>();
        for (java.lang.reflect.Method m : methods(c, "pin|verif|login|auth|valid|enter|check", "change|set|reset|new|update|balance"))
            if (m.getParameterCount() == 1 && m.getParameterTypes()[0] != java.util.Scanner.class) out.add(m);
        return out;
    }

    static String atmDeposit() throws Exception {
        Object probe = atm();
        java.util.List<java.lang.reflect.Method> deps = methods(probe.getClass(), "dep|credit|add", null);
        if (deps.isEmpty()) return "FAIL: no deposit method";
        for (java.lang.reflect.Method m : deps) {
            java.util.List<Call> plus = callsFor(m, probe, 100, true), minus = callsFor(m, probe, -100, true);
            for (int k = 0; k < plus.size(); k++) {
                Object[] r = attempt(m, plus.get(k), java.util.Collections.emptyList(), true);
                if (java.lang.Math.abs((double) r[1] - (double) r[0] - 100) > 1e-6) continue;    // not the way to call it
                Object[] r2 = attempt(m, minus.get(k), java.util.Collections.emptyList(), true);
                return (java.lang.Math.abs((double) r2[1] - (double) r2[0]) < 1e-6 ? "PASS: " : "FAIL: ")
                       + "balance went from " + round((double) r2[0]) + " to " + round((double) r2[1]);
            }
        }
        return "FAIL: depositing 100 never increased the balance";
    }

    static String atmWithdraw(boolean right) throws Exception {
        Object probe = atm();
        Class<?> c = probe.getClass();
        java.util.List<java.lang.reflect.Method> ws = methods(c, "withdraw|draw|debit", null);
        if (ws.isEmpty()) return "FAIL: no withdraw method";
        java.util.List<java.lang.reflect.Method> none = java.util.Collections.emptyList(), vs = verifiers(c);
        for (java.lang.reflect.Method m : ws) {
            java.util.List<Call> good = callsFor(m, probe, 10, true), bad = callsFor(m, probe, 10, false);
            // the ways that carry the PIN first, then the ones that need it entered separately
            for (int pass = 0; pass < 2; pass++) for (int k = 0; k < good.size(); k++) {
                if (good.get(k).pin != (pass == 0)) continue;
                java.util.List<java.lang.reflect.Method> pre = good.get(k).pin ? none : vs;
                Object[] r = attempt(m, good.get(k), pre, true);
                if (java.lang.Math.abs((double) r[0] - (double) r[1] - 10) > 1e-6) continue;    // the right PIN must take 10 off
                if (right) return "PASS: balance went from " + round((double) r[0]) + " to " + round((double) r[1]);
                if (!good.get(k).pin && vs.isEmpty()) return "FAIL: withdraw doesn't take or check a PIN";
                Object[] r2 = attempt(m, bad.get(k), pre, false);
                return (java.lang.Math.abs((double) r2[1] - (double) r2[0]) < 1e-6 ? "PASS: " : "FAIL: ")
                       + "with a wrong PIN the balance went from " + round((double) r2[0]) + " to " + round((double) r2[1]);
            }
        }
        return "FAIL: withdrawing 10 with the right PIN never reduced the balance";
    }

    // ---------------------------------------------------------------- generic checks (checks.SPECS)
    // A spec is tab-separated: the check, then its arguments. Names are regexes, case-insensitive.
    static String generic(String[] a) throws Exception {
        if (a.length > 1 && a[1].isEmpty()) {       // any of the student's classes will do
            String last = "FAIL: no classes found";
            for (Class<?> c : new java.util.ArrayList<>(classes)) {
                String[] b = a.clone();
                b[1] = java.util.regex.Pattern.quote(c.getSimpleName());
                last = generic(b);
                if (last.startsWith("PASS")) return last;
            }
            return last;
        }
        switch (a[0]) {
            case "extends": return gExtends(a[1], a[2]);
            case "abstract": { Class<?> c = cls(a[1]);
                               return isAbstract(c) && !c.isInterface() ? "PASS: " + c.getSimpleName() + " is abstract"
                                                                         : "FAIL: " + c.getSimpleName() + " is not an abstract class"; }
            case "absmethod": return gAbsMethod(a[1], a[2]);
            case "overrides": return gOverrides(a[1], a[2], Integer.parseInt(a[3]));
            case "hides": return gHides(a[1], a[2]);
            case "modifier": return gModifier(a[1], a[2], a[3]);
            case "ctors": { Class<?> c = cls(a[1]); int n = c.getDeclaredConstructors().length;
                            return (n >= Integer.parseInt(a[2]) ? "PASS: " : "FAIL: ") + c.getSimpleName() + " has " + n + " constructor(s)"; }
            case "ctorsig": return gCtorSig(a[1], a[2]);
            case "ctorparams": { Class<?> c = cls(a[1]); int most = 0;
                                 for (java.lang.reflect.Constructor<?> k : c.getDeclaredConstructors()) most = java.lang.Math.max(most, k.getParameterCount());
                                 return (most >= Integer.parseInt(a[2]) ? "PASS: " : "FAIL: ") + c.getSimpleName() + "'s constructors take at most "
                                        + most + " value(s)"; }
            case "methodsig": return gMethodSig(a[1], a[2], a[3]);
            case "overloads": return gOverloads(a[1], a[2], Integer.parseInt(a[3]));
            case "static": return gStatic(a[1], a[2], a[3]);
            case "method": { Class<?> c = cls(a[1]); java.util.List<java.lang.reflect.Method> ms = anyMethods(c, a[2]);
                             return ms.isEmpty() ? "FAIL: " + c.getSimpleName() + " has no method like " + nice(a[2]) + "()"
                                                 : "PASS: " + c.getSimpleName() + " has " + ms.get(0).getName() + "()"; }
            case "fields": return fields(a[1].split(";"), a[2].split(";"));
            case "counter": return gCounter(a[1]);
            case "value": return gValue(a[1], a[2], a[3], a[4], Double.parseDouble(a[5]), false);
            case "ctorvalue": return gValue(a[1], a[2], a[3], a[4], Double.parseDouble(a[5]), true);
            case "bank": return gBank(a[1], a[2], a[3], Double.parseDouble(a[4]), a[5], Double.parseDouble(a[6]));
            case "calc": return gCalc(a[1], a[2], a[3], a[4]);
            case "copyctor": return gCopy(a[1], a[2]);
        }
        return "FAIL: unknown check " + a[0];
    }

    static final int CI = java.util.regex.Pattern.CASE_INSENSITIVE;

    static String nice(String re) { return re.split("\\|")[0].replaceAll("[^A-Za-z ]", ""); }
    static boolean isAbstract(Class<?> c) { return java.lang.reflect.Modifier.isAbstract(c.getModifiers()); }
    static boolean isStatic(java.lang.reflect.Member m) { return java.lang.reflect.Modifier.isStatic(m.getModifiers()); }
    static boolean exact(String name, String regex) { return java.util.regex.Pattern.compile("^(?:" + regex + ")$", CI).matcher(name).find(); }

    /** The student's class for a name: one named exactly so, else the shortest name containing it. */
    static Class<?> cls(String regex) {
        for (Class<?> c : classes) if (exact(c.getSimpleName(), regex)) return c;
        Class<?> best = null;
        for (Class<?> c : classes)
            if (matches(c.getSimpleName(), regex) && (best == null || c.getSimpleName().length() < best.getSimpleName().length())) best = c;
        if (best == null) throw new Fail("no class named like " + nice(regex));
        return best;
    }

    /** Superclasses and interfaces, all the way up. */
    static java.util.List<Class<?>> ancestors(Class<?> c) {
        java.util.List<Class<?>> out = new java.util.ArrayList<>();
        java.util.ArrayDeque<Class<?>> todo = new java.util.ArrayDeque<>();
        todo.add(c);
        while (!todo.isEmpty()) {
            Class<?> k = todo.poll();
            java.util.List<Class<?>> up = new java.util.ArrayList<>(java.util.Arrays.asList(k.getInterfaces()));
            if (k.getSuperclass() != null && k.getSuperclass() != Object.class) up.add(k.getSuperclass());
            for (Class<?> u : up) if (!out.contains(u)) { out.add(u); todo.add(u); }
        }
        return out;
    }

    static boolean isA(Class<?> c, String parent) {
        for (Class<?> k : ancestors(c)) if (exact(k.getSimpleName(), parent) || matches(k.getSimpleName(), parent)) return true;
        return false;
    }

    static String gExtends(String child, String parent) throws Exception {
        Class<?> c = cls(child);
        if (!isA(c, parent))            // Manager and ManagerDemo: the one that extends counts
            for (Class<?> k : classes) if (matches(k.getSimpleName(), child) && isA(k, parent)) { c = k; break; }
        Class<?> s = c.getSuperclass();
        if (isA(c, parent)) {
            String up = (s == null || s == Object.class) ? c.getInterfaces()[0].getSimpleName() : s.getSimpleName();
            return "PASS: " + c.getSimpleName() + " extends " + up;
        }
        return "FAIL: " + c.getSimpleName() + (s == null || s == Object.class ? " doesn't extend another class"
                                                                               : " extends " + s.getSimpleName() + ", not " + nice(parent));
    }

    static String gAbsMethod(String c0, String m) throws Exception {
        Class<?> c = cls(c0);
        for (Class<?> k : withAncestors(c))
            for (java.lang.reflect.Method x : k.getDeclaredMethods())
                if (matches(x.getName(), m) && java.lang.reflect.Modifier.isAbstract(x.getModifiers()))
                    return "PASS: abstract " + x.getName() + "() in " + k.getSimpleName();
        return "FAIL: " + c.getSimpleName() + " has no abstract method like " + nice(m) + "()";
    }

    static java.util.List<Class<?>> withAncestors(Class<?> c) {
        java.util.List<Class<?>> out = new java.util.ArrayList<>(); out.add(c); out.addAll(ancestors(c)); return out;
    }

    /** A method of an ancestor that m overrides (same name and parameters, not static). */
    static boolean overridesSomething(Class<?> c, java.lang.reflect.Method m) {
        for (Class<?> k : ancestors(c))
            try { if (!isStatic(k.getDeclaredMethod(m.getName(), m.getParameterTypes()))) return true; }
            catch (NoSuchMethodException e) { }
        return false;
    }

    static String gOverrides(String p0, String m, int n) throws Exception {
        Class<?> p = cls(p0);
        java.util.List<String> who = new java.util.ArrayList<>();
        for (Class<?> c : classes) {
            if (c == p || !p.isAssignableFrom(c)) continue;
            for (java.lang.reflect.Method x : c.getDeclaredMethods())
                if (matches(x.getName(), m) && !isStatic(x) && !x.isSynthetic() && !java.lang.reflect.Modifier.isAbstract(x.getModifiers())
                        && overridesSomething(c, x)) { who.add(c.getSimpleName()); break; }
        }
        if (who.isEmpty()) return "FAIL: no subclass of " + p.getSimpleName() + " overrides " + nice(m) + "()";
        return (who.size() >= n ? "PASS: " : "FAIL: ") + nice(m) + "() overridden in " + String.join(", ", who)
               + (who.size() >= n ? "" : " (" + n + " expected)");
    }

    static String gHides(String p0, String m) throws Exception {
        Class<?> p = cls(p0);
        java.lang.reflect.Method base = null;
        for (java.lang.reflect.Method x : p.getDeclaredMethods()) if (matches(x.getName(), m) && isStatic(x)) base = x;
        if (base == null) return "FAIL: " + p.getSimpleName() + " has no static method like " + nice(m) + "()";
        java.util.List<String> who = new java.util.ArrayList<>();
        for (Class<?> c : classes)
            if (c != p && p.isAssignableFrom(c))
                try { if (isStatic(c.getDeclaredMethod(base.getName(), base.getParameterTypes()))) who.add(c.getSimpleName()); }
                catch (NoSuchMethodException e) { }
        return who.isEmpty() ? "FAIL: no subclass defines its own static " + base.getName() + "()"
                             : "PASS: static " + base.getName() + "() is redefined (hidden) in " + String.join(", ", who);
    }

    /** A field, static or not, declared in c or inherited. "bal!min" = like bal, but not like min. */
    static java.lang.reflect.Field anyField(Class<?> c, String spec) {
        String[] p = spec.split("!", 2);
        for (Class<?> k = c; k != null && k != Object.class; k = k.getSuperclass())
            for (java.lang.reflect.Field f : k.getDeclaredFields())
                if (!f.isSynthetic() && matches(f.getName(), p[0]) && (p.length == 1 || !matches(f.getName(), p[1]))) {
                    f.setAccessible(true); return f;
                }
        return null;
    }

    static String gModifier(String c0, String f0, String mod) throws Exception {
        Class<?> c = cls(c0);
        java.lang.reflect.Field f = anyField(c, f0);
        if (f == null) return "FAIL: " + c.getSimpleName() + " has no field like " + nice(f0);
        int m = f.getModifiers();
        String is = java.lang.reflect.Modifier.isPrivate(m) ? "private" : java.lang.reflect.Modifier.isProtected(m) ? "protected"
                  : java.lang.reflect.Modifier.isPublic(m) ? "public" : "package-private (no modifier)";
        return (is.equals(mod) ? "PASS: " : "FAIL: ") + f.getName() + " is " + is;
    }

    static boolean kind(Class<?> t, String k, Class<?> self) {
        switch (k) {
            case "int": return t == int.class || t == Integer.class;
            case "long": return t == long.class || t == Long.class;
            case "double": return t == double.class || t == Double.class;
            case "float": return t == float.class || t == Float.class;
            case "short": return t == short.class || t == Short.class;
            case "char": return t == char.class || t == Character.class;
            case "num": return isNumeric(t);
            case "text": return t == String.class;
            case "same": return t == self;
            default: return true;
        }
    }

    /** Parameter types against a list of kinds, in any order: "text,num" fits (String, double) and (int, String). */
    static boolean sigMatch(Class<?>[] ts, String sig, Class<?> self) {
        String[] ks = sig.trim().isEmpty() ? new String[0] : sig.split(",");
        if (ks.length != ts.length) return false;
        boolean[] used = new boolean[ts.length];
        for (String k : ks) {
            int hit = -1;
            for (int i = 0; i < ts.length && hit < 0; i++) if (!used[i] && kind(ts[i], k.trim(), self)) hit = i;
            if (hit < 0) return false;
            used[hit] = true;
        }
        return true;
    }

    static String show(String sig) { return sig.trim().isEmpty() ? "no arguments" : sig.replace("text", "String").replace("num", "number"); }

    static String gCtorSig(String c0, String sigs) throws Exception {
        Class<?> c = cls(c0);
        java.util.List<String> missing = new java.util.ArrayList<>();
        for (String s : sigs.split(";", -1)) {
            boolean found = false;
            for (java.lang.reflect.Constructor<?> k : c.getDeclaredConstructors()) if (sigMatch(k.getParameterTypes(), s, c)) found = true;
            if (!found) missing.add("(" + show(s) + ")");
        }
        return missing.isEmpty() ? "PASS: " + c.getSimpleName() + " has all the constructors"
                                 : "FAIL: " + c.getSimpleName() + " has no constructor " + String.join(", ", missing);
    }

    static java.util.List<java.lang.reflect.Method> anyMethods(Class<?> c, String regex) {
        java.util.List<java.lang.reflect.Method> out = new java.util.ArrayList<>();
        for (Class<?> k : withAncestors(c))
            for (java.lang.reflect.Method m : k.getDeclaredMethods())
                if (!m.isSynthetic() && matches(m.getName(), regex)) { m.setAccessible(true); out.add(m); }
        // the exact name first: area() before surfaceArea()
        out.sort((x, y) -> Boolean.compare(!exact(x.getName(), regex), !exact(y.getName(), regex)));
        return out;
    }

    static String gMethodSig(String c0, String m, String sigs) throws Exception {
        Class<?> c = cls(c0);
        java.util.List<String> missing = new java.util.ArrayList<>();
        for (String s : sigs.split(";", -1)) {
            boolean found = false;
            for (java.lang.reflect.Method x : anyMethods(c, m)) if (sigMatch(x.getParameterTypes(), s, c)) found = true;
            if (!found) missing.add(nice(m) + "(" + show(s) + ")");
        }
        return missing.isEmpty() ? "PASS: " + c.getSimpleName() + " has all the versions of " + nice(m) + "()"
                                 : "FAIL: " + c.getSimpleName() + " has no " + String.join(", ", missing);
    }

    static String gOverloads(String c0, String m, int n) throws Exception {
        Class<?> c = cls(c0);
        java.util.Set<String> sigs = new java.util.LinkedHashSet<>();
        for (java.lang.reflect.Method x : anyMethods(c, m))
            sigs.add(x.getName() + java.util.Arrays.toString(x.getParameterTypes()));
        java.util.Set<String> names = new java.util.TreeSet<>();
        for (String s : sigs) names.add(s.substring(0, s.indexOf('[')));
        return (sigs.size() >= n ? "PASS: " : "FAIL: ") + sigs.size() + " version(s) of " + String.join("/", names.isEmpty() ? java.util.List.of(nice(m)) : names)
               + "() in " + c.getSimpleName() + (sigs.size() >= n ? "" : " (" + n + " expected)");
    }

    static String gStatic(String c0, String member, String what) throws Exception {
        Class<?> c = cls(c0);
        for (Class<?> k : withAncestors(c)) {
            if (what.equals("field")) {
                for (java.lang.reflect.Field f : k.getDeclaredFields())
                    if (matches(f.getName(), member) && isStatic(f)) return "PASS: static " + f.getName() + " in " + k.getSimpleName();
            } else {
                for (java.lang.reflect.Method m : k.getDeclaredMethods())
                    if (matches(m.getName(), member) && isStatic(m)) return "PASS: static " + m.getName() + "() in " + k.getSimpleName();
            }
        }
        return "FAIL: " + c.getSimpleName() + " has no static " + (what.equals("field") ? "variable" : "method") + " like " + nice(member);
    }

    static Class<?> concrete(Class<?> base) {
        if (!isAbstract(base) && !base.isInterface()) return base;
        for (Class<?> c : classes) if (base.isAssignableFrom(c) && !isAbstract(c) && !c.isInterface()) return c;
        throw new Fail("no class that can be created from " + base.getSimpleName());
    }

    static String gCounter(String b0) throws Exception {
        Class<?> b = cls(b0);
        java.lang.reflect.Field cnt = null;
        for (Class<?> k : withAncestors(b))
            for (java.lang.reflect.Field f : k.getDeclaredFields())
                if (isStatic(f) && isNumeric(f.getType()) && !java.lang.reflect.Modifier.isFinal(f.getModifiers())
                        && (cnt == null || matches(f.getName(), "total|count|num|no"))) { f.setAccessible(true); cnt = f; }
        if (cnt == null) return "FAIL: " + b.getSimpleName() + " has no static counter";
        Class<?> sub = concrete(b);
        double before = ((java.lang.Number) cnt.get(null)).doubleValue();
        make(sub, 1000); make(sub, 1000);
        double after = ((java.lang.Number) cnt.get(null)).doubleValue();
        return (after - before == 2 ? "PASS: " : "FAIL: ") + cnt.getName() + " went from " + amt(before) + " to " + amt(after)
               + " when 2 " + sub.getSimpleName() + " objects were created";
    }

    /** An object of c from these numbers: a constructor taking exactly that many numbers (in
     *  order), else any constructor. With strict, only the exact constructor will do. */
    static Object build(Class<?> c, double[] vals, boolean strict) throws Exception {
        for (java.lang.reflect.Constructor<?> k : c.getDeclaredConstructors()) {
            Class<?>[] ts = k.getParameterTypes();
            if (ts.length != vals.length) continue;
            boolean ok = true; for (Class<?> t : ts) ok &= isNumeric(t);
            if (!ok) continue;
            Object[] args = new Object[ts.length];
            for (int i = 0; i < ts.length; i++) args[i] = cast(vals[i], ts[i]);
            k.setAccessible(true);
            try { return k.newInstance(args); } catch (Throwable t) { if (strict) throw new Fail("the constructor failed (" + cause(t) + ")"); }
        }
        if (strict) throw new Fail("no " + c.getSimpleName() + " constructor taking " + vals.length + " number(s)");
        return make(c, vals.length > 0 ? vals[0] : 1);
    }

    /** Everything m gives for o: its return value and every number it prints. */
    static java.util.List<Double> results(java.lang.reflect.Method m, Object o, Object... a) throws Exception {
        java.util.List<Double> out = new java.util.ArrayList<>();
        captured.reset();
        Object r;
        try { r = m.invoke(isStatic(m) ? null : o, a); } catch (java.lang.reflect.InvocationTargetException e) { return out; }
        if (r instanceof java.lang.Number) out.add(((java.lang.Number) r).doubleValue());
        java.util.regex.Matcher mm = java.util.regex.Pattern.compile("-?\\d+(?:\\.\\d+)?(?:[eE]-?\\d+)?").matcher(captured.toString());
        while (mm.find()) out.add(Double.parseDouble(mm.group()));
        return out;
    }

    static boolean near(double got, double want, double tolPct) {
        return java.lang.Math.abs(got - want) <= java.lang.Math.max(0.011, java.lang.Math.abs(want) * tolPct / 100);
    }

    static String gValue(String c0, String assign, String m, String expect, double tol, boolean strict) throws Exception {
        Class<?> c = concrete(cls(c0));
        String[] parts = assign.trim().isEmpty() ? new String[0] : assign.split(";");
        double[] vals = new double[parts.length];
        String[] names = new String[parts.length];
        for (int i = 0; i < parts.length; i++) { String[] kv = parts[i].split("=", 2); names[i] = kv[0]; vals[i] = Double.parseDouble(kv[1]); }
        Object o = build(c, vals, strict);
        if (!strict)
            for (int i = 0; i < vals.length; i++) {
                java.lang.reflect.Field f = anyField(c, names[i]);
                if (f != null && isNumeric(f.getType()) && !isStatic(f)) set(o, f, vals[i]);
            }
        String[] wants = expect.split("\\|");
        java.util.List<Double> seen = new java.util.ArrayList<>();
        for (java.lang.reflect.Method x : anyMethods(c, m)) {
            if (x.getParameterCount() == 0) seen.addAll(results(x, o));
            else if (numericArgs(x, 1) && vals.length > 0) seen.addAll(results(x, o, cast(vals[0], x.getParameterTypes()[0])));
            else continue;
            for (double g : seen) for (String w : wants) if (near(g, Double.parseDouble(w), tol))
                return "PASS: " + x.getName() + "() gave " + round(g) + " for " + (assign.isEmpty() ? "the no-argument constructor" : assign.replaceAll("\\|[^=;]*", "").replace(";", ", "));
        }
        if (anyMethods(c, m).isEmpty()) return "FAIL: " + c.getSimpleName() + " has no method like " + nice(m) + "()";
        return "FAIL: expected " + wants[0] + " for " + (assign.isEmpty() ? "the no-argument constructor" : assign.replaceAll("\\|[^=;]*", "").replace(";", ", "))
               + (seen.isEmpty() ? ", got nothing" : ", got " + round(seen.get(seen.size() - 1)));
    }

    /** Set fields, call a money method with an amount, and look at a field afterwards. */
    static String gBank(String c0, String assign, String m, double amount, String fieldSpec, double want) throws Exception {
        Class<?> c = concrete(cls(c0));
        java.util.List<java.lang.reflect.Method> ms = anyMethods(c, m);
        if (ms.isEmpty()) return "FAIL: " + c.getSimpleName() + " has no method like " + nice(m) + "()";
        ms.sort((x, y) -> x.getParameterCount() - y.getParameterCount());     // deposit(amount) first
        java.lang.reflect.Field target = anyField(c, fieldSpec);
        if (target == null || !isNumeric(target.getType())) return "FAIL: " + c.getSimpleName() + " has no field like " + nice(fieldSpec);
        for (java.lang.reflect.Method x : ms) {
            Class<?>[] ts = x.getParameterTypes();
            Object[] args = new Object[ts.length];
            boolean ok = ts.length > 0 && isNumeric(ts[0]);
            for (int i = 1; i < ts.length && ok; i++) { args[i] = arg(ts[i], amount); ok = args[i] != null; }
            if (!ok && ts.length != 0) continue;
            if (ts.length > 0) args[0] = cast(amount, ts[0]);
            feed(amt(amount) + "\n");
            Object o = make(c, 1000);
            for (String kv : assign.split(";")) {
                if (kv.trim().isEmpty()) continue;
                String[] p = kv.split("=", 2);
                java.lang.reflect.Field f = anyField(c, p[0]);
                if (f == null) return "FAIL: " + c.getSimpleName() + " has no field like " + nice(p[0]);
                set(o, f, Double.parseDouble(p[1]));
            }
            invoke(x, o, args);
            double got = get(o, target);
            return (near(got, want, 0) ? "PASS: " : "FAIL: ") + "after " + x.getName() + "(" + amt(amount) + ") " + target.getName()
                   + " is " + round(got) + " (expected " + amt(want) + ")";
        }
        return "FAIL: no way to call " + nice(m) + "() with an amount";
    }

    /** Call the version of m whose parameters fit these numbers; all the wanted numbers must
     *  be returned or printed. */
    static String gCalc(String c0, String m, String argList, String expect) throws Exception {
        Class<?> c = concrete(cls(c0));
        String[] as = argList.split(",");
        boolean dec = argList.contains(".");
        for (java.lang.reflect.Method x : anyMethods(c, m)) {
            Class<?>[] ts = x.getParameterTypes();
            if (ts.length != as.length) continue;
            boolean fits = true;
            for (Class<?> t : ts) fits &= dec ? (t == double.class || t == float.class || t == Double.class) : (t == int.class || t == Integer.class);
            if (!fits) continue;
            Object[] args = new Object[ts.length];
            for (int i = 0; i < ts.length; i++) args[i] = cast(Double.parseDouble(as[i]), ts[i]);
            Object o = isStatic(x) ? null : make(c, 1);
            java.util.List<Double> got = results(x, o, args);
            java.util.List<String> missing = new java.util.ArrayList<>();
            for (String w : expect.split(",")) {
                boolean hit = false; for (double g : got) hit |= near(g, Double.parseDouble(w), 0.5);
                if (!hit) missing.add(w);
            }
            return (missing.isEmpty() ? "PASS: " : "FAIL: ") + x.getName() + "(" + argList.replace(",", ", ") + ")"
                   + (missing.isEmpty() ? " gave " + expect.replace(",", " and ") : " didn't give " + String.join(" or ", missing));
        }
        return "FAIL: no " + nice(m) + "() taking " + as.length + " " + (dec ? "double" : "int") + " values";
    }

    static String gCopy(String c0, String priceSpec) throws Exception {
        Class<?> c = cls(c0);
        java.lang.reflect.Constructor<?> copy = null;
        for (java.lang.reflect.Constructor<?> k : c.getDeclaredConstructors())
            if (k.getParameterCount() == 1 && k.getParameterTypes()[0] == c) copy = k;
        if (copy == null) return "FAIL: " + c.getSimpleName() + " has no copy constructor " + c.getSimpleName() + "(" + c.getSimpleName() + " other)";
        java.lang.reflect.Field pf = anyField(c, priceSpec);
        Object a = make(c, 1000);
        if (pf != null && isNumeric(pf.getType())) set(a, pf, 1000);
        copy.setAccessible(true);
        Object b = copy.newInstance(a);
        if (pf == null || !isNumeric(pf.getType())) return "PASS: copy constructor found";
        double got = get(b, pf);
        return (near(got, 1000, 0) || near(got, 850, 0) ? "PASS: " : "FAIL: ") + "the copy of a phone priced 1000 has "
               + pf.getName() + " " + round(got);
    }
}
'''
