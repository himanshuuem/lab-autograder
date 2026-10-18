"""Read a PDF into positioned text lines.

Code pasted into Google Docs / Word and exported to PDF often loses its
leading spaces: indentation survives only as the x-position of the first
character. So every line keeps the x of its first non-space character, and
indentation is rebuilt later from those positions.

Scanned pages (photos / prints of code) fall back to Tesseract OCR.
"""
from __future__ import annotations

import re
import statistics
from dataclasses import dataclass, field

import pymupdf

MONO_HINTS = ("mono", "courier", "consol", "code", "menlo", "fixed", "source code")
_LEAD_NUM = re.compile(r"^(\s*)(\d{1,4})([.:)|]?)(\s+)")


@dataclass
class Line:
    text: str               # leading whitespace removed
    x: float                # x (pt) of first non-space character
    y: float                # baseline y (pt) from the top of the page
    page: int               # 1-based
    page_h: float
    mono: bool
    char_w: float           # estimated width of one character / space (pt)
    x_after_num: float | None = None  # x of the code after a leading line number
    conf: float | None = None         # OCR confidence 0-100, None for text PDFs
    ocr: bool = False
    image: bool = False               # read from a picture inside the page (a screenshot)


@dataclass
class ReadResult:
    lines: list[Line] = field(default_factory=list)
    ocr_pages: list[int] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    page_count: int = 0
    images_read: int = 0     # screenshots inside pages that were OCR'd


def _is_mono(fonts: set[str], widths: list[float]) -> bool:
    if any(h in f.lower() for f in fonts for h in MONO_HINTS):
        return True
    if len(widths) >= 6:
        mean = statistics.mean(widths)
        return mean > 0 and statistics.pstdev(widths) / mean < 0.04
    return False


def _build_line(chars: list[tuple], page: int, page_h: float) -> Line | None:
    """chars: (c, x0, x1, y, size, font[, span_x0, seq]). Runs (spans) are ordered by
    position, but letters inside a run keep the PDF's own order: a ligature such as "ti"
    can leave a zero-width letter at the same x as the next one."""
    chars.sort(key=lambda t: (t[6], t[7]) if len(t) > 7 else (t[1], 0))
    visible = [t for t in chars if not t[0].isspace()]
    if not visible:
        return None
    fonts = {t[5] for t in visible}
    widths = [t[2] - t[1] for t in visible if t[2] > t[1]]
    mono = _is_mono(fonts, widths)
    size = statistics.median(t[4] for t in visible)
    if mono and widths:
        char_w = statistics.median(widths)
    else:
        char_w = size * 0.28  # typical space width in proportional fonts
    char_w = max(char_w, 1.0)

    out, prev_x1 = [], None
    for c, x0, x1, *_ in chars:
        if c.isspace():
            continue
        if prev_x1 is not None:
            gap = x0 - prev_x1
            if gap > 0.5 * char_w:
                out.append(" " * max(1, round(gap / char_w)))
        out.append(c)
        prev_x1 = x1 if prev_x1 is None else max(prev_x1, x1)
    text = "".join(out)

    x_after = None
    m = _LEAD_NUM.match(text)
    if m:
        skip = len(m.group(2)) + len(m.group(3))
        seen = 0
        for t in visible:
            if seen == skip:
                x_after = t[1]
                break
            seen += 1
    return Line(text=text, x=visible[0][1], y=visible[0][3], page=page,
                page_h=page_h, mono=mono, char_w=char_w, x_after_num=x_after)


def _text_lines(page, pno: int) -> list[Line]:
    flags = pymupdf.TEXT_PRESERVE_WHITESPACE | pymupdf.TEXT_MEDIABOX_CLIP
    raw = page.get_text("rawdict", flags=flags)
    chars = []
    for block in raw.get("blocks", []):
        for ln in block.get("lines", []):
            for span in ln.get("spans", []):
                sch = span.get("chars", [])
                span_x = min((ch["bbox"][0] for ch in sch), default=0.0)
                for ch in sch:
                    x0, _, x1, _ = ch["bbox"]
                    chars.append((ch["c"], x0, x1, ch["origin"][1],
                                  span["size"], span["font"], span_x, len(chars)))
    # group characters into visual lines by baseline
    chars.sort(key=lambda t: (t[3], t[1]))
    groups: list[list[tuple]] = []
    for t in chars:
        if groups and abs(groups[-1][0][3] - t[3]) <= max(1.5, 0.3 * t[4]):
            groups[-1].append(t)
        else:
            groups.append([t])
    lines = [_build_line(g, pno, page.rect.height) for g in groups]
    return [ln for ln in lines if ln]


def _prepare(img):
    """Grayscale, invert dark screenshots (terminals, dark IDEs), stretch contrast,
    and enlarge small text: all of which help Tesseract a lot."""
    from PIL import ImageOps, ImageStat
    g = ImageOps.grayscale(img)
    if ImageStat.Stat(g).mean[0] < 110:
        g = ImageOps.invert(g)
    g = ImageOps.autocontrast(g, cutoff=1)
    if g.height < 900:
        f = min(3.0, 900 / max(g.height, 1))
        g = g.resize((int(g.width * f), int(g.height * f)))
    return g


def _ocr_image(img, *, x0: float, y0: float, scale: float, pno: int, page_h: float,
               image: bool, scale_y: float | None = None) -> list[Line]:
    """OCR a PIL image whose top-left sits at (x0, y0) pt on the page; `scale` is
    points per image pixel."""
    import pytesseract
    scale_y = scale if scale_y is None else scale_y   # a picture stretched in Word has its own
    img_h_pt = img.height * scale_y                    # vertical scale
    if image:
        before = img.width
        img = _prepare(img)
        scale, scale_y = scale * before / img.width, scale_y * before / img.width
    # psm 6 = uniform block of text; keeps code and output lines intact
    data = pytesseract.image_to_data(img, config="--psm 6 -c preserve_interword_spaces=1",
                                     output_type=pytesseract.Output.DICT)
    words: dict[tuple, list] = {}
    for i, w in enumerate(data["text"]):
        if not w.strip() or float(data["conf"][i]) < 0:
            continue
        key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
        words.setdefault(key, []).append(
            (x0 + data["left"][i] * scale, data["width"][i] * scale,
             y0 + data["top"][i] * scale_y, data["height"][i] * scale_y,
             w, float(data["conf"][i])))
    lines = []
    for ws in words.values():
        ws.sort(key=lambda t: t[0])
        if image:   # an IDE's indent guides read as "|" before the code: they also run tall
            while len(ws) > 1 and _GUIDE.match(ws[0][4]):
                ws.pop(0)
        char_w = statistics.median(t[1] / max(len(t[4]), 1) for t in ws)
        char_w = max(char_w, 0.5)
        parts, prev_end = [], None
        for left, width, _, _, w, _ in ws:
            if prev_end is not None:
                # word boxes exclude side bearings, so one space measures ~1.4 chars
                parts.append(" " * max(1, round((left - prev_end) / char_w - 0.5)))
            parts.append(w)
            prev_end = left + width
        text = "".join(parts)
        x_after = None
        m = _LEAD_NUM.match(text)
        if m and len(ws) > 1 and ws[0][4].rstrip(".:)|").isdigit():
            x_after = ws[1][0]
        conf = statistics.mean(t[5] for t in ws)
        if image and conf < 30 and not _BRACES.match(text):   # icons, window chrome, noise
            continue                  # (a "}" alone is read with low confidence but matters)
        # a window title bar: top of the screenshot, a few junk glyphs (the OCR'd
        # close/minimise buttons), a wide gap, then the title
        if image and (ws[0][2] - y0) < 0.14 * img_h_pt and _TITLE_BAR.match(text):
            continue
        lines.append(Line(text=text, x=ws[0][0], y=ws[0][2] + ws[0][3],
                          page=pno, page_h=page_h, mono=False,
                          char_w=char_w, x_after_num=x_after,
                          conf=conf, ocr=True, image=image))
    lines.sort(key=lambda ln: (ln.y, ln.x))
    return lines


def _ocr_lines(page, pno: int, dpi: int = 300) -> list[Line]:
    """OCR a whole page (a scan or photo)."""
    from PIL import Image
    pix = page.get_pixmap(dpi=dpi)
    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    return _ocr_image(img, x0=0, y0=0, scale=72.0 / dpi, pno=pno, page_h=page.rect.height, image=False)


_GUIDE = re.compile(r"^[|¦]+$")
_BRACES = re.compile(r"^\s*[{}]+[;)]?\s*$")
_TITLE_BAR = re.compile(r"^\s*(\S{1,4}\s+){0,3}\S{0,4}\s{4,}\S+(\s+\S+){0,4}\s*$")
MIN_IMAGE_PT = (60, 18)   # smaller pictures are icons/logos, not screenshots


def _original_pixels(page, info):
    """The screenshot exactly as the student pasted it (no re-rendering blur),
    when it is placed upright and unclipped."""
    import io
    from PIL import Image
    xref = info.get("xref") or 0
    t = info.get("transform") or (1, 0, 0, 1, 0, 0)
    if xref <= 0 or abs(t[1]) > 1e-3 or abs(t[2]) > 1e-3 or t[0] <= 0:
        return None
    full = pymupdf.Rect(info["bbox"])
    if not page.rect.contains(full):
        return None
    try:
        raw = page.parent.extract_image(xref)
        img = Image.open(io.BytesIO(raw["image"]))
        if img.mode in ("RGBA", "LA", "P"):
            bg = Image.new("RGB", img.size, (255, 255, 255))
            img = img.convert("RGBA")
            bg.paste(img, mask=img.split()[-1])
            return bg
        return img.convert("RGB")
    except Exception:
        return None


def _screenshot_lines(page, pno: int) -> tuple[list[Line], int]:
    """OCR every picture placed on a text page (output or code screenshots)."""
    from PIL import Image
    out, n = [], 0
    seen = set()
    for info in page.get_image_info(xrefs=True):
        r = pymupdf.Rect(info["bbox"]) & page.rect
        if r.is_empty or r.width < MIN_IMAGE_PT[0] or r.height < MIN_IMAGE_PT[1]:
            continue
        key = tuple(round(v) for v in r)
        if key in seen:
            continue
        seen.add(key)
        img = _original_pixels(page, info)
        if img is None:   # no usable original: render that part of the page
            native = max(info.get("width") or 0, 1)
            dpi = int(min(600, max(200, native / (r.width / 72.0))))
            pix = page.get_pixmap(dpi=dpi, clip=r)
            img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        lines = _ocr_image(img, x0=r.x0, y0=r.y0, scale=r.width / img.width, scale_y=r.height / img.height, pno=pno,
                           page_h=page.rect.height, image=True)
        if lines:
            n += 1
            out.extend(lines)
    return out, n


def _needs_ocr(page, lines: list[Line]) -> bool:
    """A scanned or photographed page: almost no text, and pictures cover most of it.
    (A screenshot alone on a page is read as a screenshot instead.) A page with a
    heading such as "QUE 2)" or "OUTPUT:" beside its pictures is a document with pasted
    screenshots, read one by one (a dark IDE screenshot is inverted first), unless one
    picture fills the page edge to edge (a scan with a "Scanned with…" line)."""
    n_chars = sum(len(ln.text) for ln in lines)
    if n_chars >= 25:
        return False
    # typed text drawn as vector shapes ("print to PDF" with fonts as outlines): no text
    # layer, but a path per glyph (a short page of code is still 50+)
    if len(page.get_drawings()) >= 50:
        return True
    area = page.rect.width * page.rect.height
    pictures = [(pymupdf.Rect(i["bbox"]) & page.rect).get_area() for i in page.get_image_info()]
    pictures = [a for a in pictures if a > 0]
    if not pictures:
        return False
    if lines:
        return max(pictures) >= 0.85 * area
    return sum(pictures) >= 0.5 * area


def read_pdf(path: str, ocr: str = "auto") -> ReadResult:
    """ocr: 'auto' (scanned pages, and screenshots placed on text pages),
    'always' (OCR every page as a picture), or 'never'."""
    res = ReadResult()
    try:
        doc = pymupdf.open(path)
    except Exception as e:  # corrupt / not a PDF
        raise ValueError(f"cannot open PDF {path!r}: {e}") from e
    with doc:
        if doc.needs_pass:
            raise ValueError("PDF is password-protected")
        res.page_count = doc.page_count
        for i, page in enumerate(doc, start=1):
            lines = _text_lines(page, i)
            if ocr == "always" or (ocr == "auto" and _needs_ocr(page, lines)):
                try:
                    lines = _ocr_lines(page, i)
                    res.ocr_pages.append(i)
                except Exception as e:
                    res.warnings.append(f"page {i}: OCR failed ({e.__class__.__name__}: {e})")
            elif ocr == "auto" and page.get_images():
                try:
                    shots, n = _screenshot_lines(page, i)
                    if shots:
                        res.images_read += n
                        lines = sorted(lines + shots, key=lambda ln: (ln.y, ln.x))
                except Exception as e:
                    res.warnings.append(f"page {i}: could not read a screenshot ({e.__class__.__name__}: {e})")
            res.lines.extend(lines)
    return res
