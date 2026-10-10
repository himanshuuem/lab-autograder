"""Rebuild indentation from x-positions."""
from __future__ import annotations

from .pdfread import Line


def _join(lines: list[Line], indents: list[int]) -> str:
    """Join lines, putting back blank lines where the vertical gap shows one."""
    gaps = [b.y - a.y for a, b in zip(lines, lines[1:]) if b.page == a.page and b.y > a.y]
    step = sorted(gaps)[(len(gaps) - 1) // 2] if gaps else 0  # lower median = one line
    out = []
    for i, (ln, n) in enumerate(zip(lines, indents)):
        if i and step and ln.page == lines[i - 1].page:
            extra = round((ln.y - lines[i - 1].y) / step) - 1
            out.extend([""] * max(0, min(extra, 2)))
        out.append(" " * n + ln.text)
    return "\n".join(out)


def by_width(lines: list[Line]) -> str:
    """indent = (x - leftmost x) / char width. Exact for monospace fonts."""
    if not lines:
        return ""
    x0 = min(ln.x for ln in lines)
    cw = sorted(ln.char_w for ln in lines)[len(lines) // 2]
    return _join(lines, [max(0, round((ln.x - x0) / cw)) for ln in lines])


def by_levels(lines: list[Line], step: int = 4) -> str:
    """Cluster distinct x-positions into nesting levels, `step` spaces each.
    Robust when code was typed in a proportional font (Arial, Calibri)."""
    if not lines:
        return ""
    cw = sorted(ln.char_w for ln in lines)[len(lines) // 2]
    tol = max(1.5, 0.6 * cw)
    centers: list[float] = []
    for x in sorted(ln.x for ln in lines):
        if not centers or x - centers[-1] > tol:
            centers.append(x)
    def level(x: float) -> int:
        return min(range(len(centers)), key=lambda i: abs(centers[i] - x))
    return _join(lines, [step * level(ln.x) for ln in lines])


def rebuild(lines: list[Line]) -> str:
    """Best default: exact widths for monospace code, nesting levels otherwise."""
    mono = sum(ln.mono for ln in lines) >= len(lines) / 2
    return by_width(lines) if mono else by_levels(lines)


def python_compiles(src: str) -> tuple[bool, str | None]:
    """Syntax check only: compile() never executes the code."""
    if len(src) > 200_000:
        return False, "source too large to check"
    try:
        compile(src, "<submission>", "exec", dont_inherit=True)
        return True, None
    except SyntaxError as e:
        return False, f"line {e.lineno}: {e.msg}"
    except (ValueError, RecursionError, MemoryError) as e:
        return False, f"{e.__class__.__name__}"
