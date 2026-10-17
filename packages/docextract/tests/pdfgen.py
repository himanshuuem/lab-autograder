"""Build PDFs that look like real student submissions.

Blocks:
  ("h", text)                    heading (bold, proportional)
  ("p", text)                    prose paragraph line
  ("code", text, style)          style: "mono_spaces"  - Courier with real spaces
                                        "mono_offset"  - Courier, spaces dropped, x-offset (Docs export)
                                        "prop_offset"  - Arial-like, spaces dropped, x-offset
                                        "numbered"     - IDE screenshot style with line numbers
  ("pagebreak",)
"""
from __future__ import annotations

import io

import pymupdf
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

_FONTS = {
    "Sans": "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "SansB": "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "Mono": "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
}
for _n, _p in _FONTS.items():
    if _n not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(_n, _p))

LEFT, TOP, LH, SIZE = 60, 60, 15, 10.5


def screenshot(text: str, dark: bool = True, font_px: int = 15, title: str | None = "Terminal") -> bytes:
    """A PNG that looks like a terminal / IDE console screenshot."""
    from PIL import Image, ImageDraw, ImageFont
    font = ImageFont.truetype(_FONTS["Mono"], font_px)
    lines = text.split("\n")
    lh = int(font_px * 1.45)
    w = max(360, max(int(font.getlength(l)) for l in lines) + 40)
    top = 34 if title else 12
    h = top + lh * len(lines) + 16
    bg, fg = ((30, 30, 30), (220, 220, 220)) if dark else ((255, 255, 255), (20, 20, 20))
    img = Image.new("RGB", (w, h), bg)
    d = ImageDraw.Draw(img)
    if title:   # window title bar with traffic lights
        d.rectangle([0, 0, w, 24], fill=(60, 60, 60) if dark else (225, 225, 225))
        for i, c in enumerate([(255, 95, 86), (255, 189, 46), (39, 201, 63)]):
            d.ellipse([10 + i * 18, 7, 20 + i * 18, 17], fill=c)
        d.text((w // 2 - 30, 4), title, font=ImageFont.truetype(_FONTS["Sans"], 12), fill=fg)
    for i, l in enumerate(lines):
        d.text((16, top + i * lh), l, font=font, fill=fg)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def make_pdf(path, blocks, header: str | None = None, footer_pages: bool = True) -> str:
    w, h = A4
    c = canvas.Canvas(str(path), pagesize=A4)
    y = h - TOP
    page = 1

    def deco():
        if header:
            c.setFont("Sans", 8); c.drawString(LEFT, h - 25, header)
        if footer_pages:
            c.setFont("Sans", 8); c.drawString(w / 2, 20, f"Page {page}")

    def newpage():
        nonlocal y, page
        deco(); c.showPage(); page += 1; y = h - TOP

    for b in blocks:
        if b[0] == "pagebreak":
            newpage(); continue
        if b[0] == "img":   # ("img", png_bytes, width_pt)
            from reportlab.lib.utils import ImageReader
            ir = ImageReader(io.BytesIO(b[1]))
            iw, ih = ir.getSize()
            dw = b[2] if len(b) > 2 else min(w - 2 * LEFT, iw * 0.5)
            dh = dw * ih / iw
            if y - dh < 50: newpage()
            c.drawImage(ir, LEFT, y - dh + LH * 0.7, width=dw, height=dh)
            y -= dh + 8
            continue
        if b[0] in ("h", "p"):
            for line in b[1].split("\n"):
                if y < 60: newpage()
                c.setFont("SansB" if b[0] == "h" else "Sans", 12 if b[0] == "h" else SIZE)
                c.drawString(LEFT, y, line); y -= LH + (4 if b[0] == "h" else 0)
            continue
        _, text, style = b
        font = "Sans" if style == "prop_offset" else "Mono"
        for n, line in enumerate(text.split("\n"), 1):
            if y < 60: newpage()
            if not line.strip():
                y -= LH; continue
            c.setFont(font, SIZE)
            stripped = line.lstrip(" ")
            nsp = len(line) - len(stripped)
            if style == "mono_spaces":
                c.drawString(LEFT, y, line)
            elif style == "numbered":
                c.drawString(LEFT, y, f"{n:>3}")
                c.drawString(LEFT + 30 + nsp * pdfmetrics.stringWidth(" ", font, SIZE), y, stripped)
            else:
                c.drawString(LEFT + nsp * pdfmetrics.stringWidth(" ", font, SIZE), y, stripped)
            y -= LH
    deco(); c.save()
    return str(path)


def make_outlined(src_pdf, dst_pdf) -> str:
    """Draw every glyph as a vector path, as some "print to PDF" tools do: the pages
    look typed but have no text layer and no pictures."""
    src = pymupdf.open(src_pdf)
    out = pymupdf.open()
    for page in src:
        svg = page.get_svg_image(text_as_path=True)
        out.insert_pdf(pymupdf.open(stream=pymupdf.open(stream=svg.encode(), filetype="svg").convert_to_pdf()))
    out.save(dst_pdf)
    return str(dst_pdf)


def make_scanned(src_pdf, dst_pdf, dpi: int = 200) -> str:
    """Rasterise every page: the result has images only, no text layer."""
    src = pymupdf.open(src_pdf)
    out = pymupdf.open()
    for page in src:
        pix = page.get_pixmap(dpi=dpi)
        p = out.new_page(width=page.rect.width, height=page.rect.height)
        p.insert_image(p.rect, stream=pix.tobytes("png"))
    out.save(dst_pdf)
    return str(dst_pdf)
