"""Generate PDFs that look like real submissions (built-in fonts only)."""
from __future__ import annotations

import io

from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfgen import canvas

LEFT, TOP, LH, SIZE = 60, 60, 15, 10.5


MONO_TTF = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
SANS_TTF = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"


def screenshot(text: str, dark: bool = True, font_px: int = 15, title: str | None = "Terminal") -> bytes:
    """A PNG that looks like a terminal or IDE console screenshot."""
    from PIL import Image, ImageDraw, ImageFont
    try:
        font = ImageFont.truetype(MONO_TTF, font_px)
        small = ImageFont.truetype(SANS_TTF, 12)
    except OSError:
        font = small = ImageFont.load_default()
    lines = text.split("\n")
    lh = int(font_px * 1.45)
    w = max(360, max(int(font.getlength(l)) for l in lines) + 40)
    top = 34 if title else 12
    h = top + lh * len(lines) + 16
    bg, fg = ((30, 30, 30), (220, 220, 220)) if dark else ((255, 255, 255), (20, 20, 20))
    img = Image.new("RGB", (w, h), bg)
    d = ImageDraw.Draw(img)
    if title:
        d.rectangle([0, 0, w, 24], fill=(60, 60, 60) if dark else (225, 225, 225))
        for i, c in enumerate([(255, 95, 86), (255, 189, 46), (39, 201, 63)]):
            d.ellipse([10 + i * 18, 7, 20 + i * 18, 17], fill=c)
        d.text((w // 2 - 30, 4), title, font=small, fill=fg)
    for i, l in enumerate(lines):
        d.text((16, top + i * lh), l, font=font, fill=fg)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def make_docx(blocks) -> bytes:
    """A Word file: ("h", text) | ("p", text) | ("code", text, font) | ("img", png, width_in)."""
    import docx
    from docx.shared import Inches, Pt
    d = docx.Document()
    for b in blocks:
        if b[0] == "h":
            d.add_heading(b[1], level=2)
        elif b[0] == "p":
            d.add_paragraph(b[1])
        elif b[0] == "code":
            for line in b[1].split("\n"):
                para = d.add_paragraph()
                para.paragraph_format.space_after = Pt(0)
                run = para.add_run(line)
                run.font.name, run.font.size = b[2], Pt(10)
        elif b[0] == "img":
            d.add_picture(io.BytesIO(b[1]), width=Inches(b[2] if len(b) > 2 else 4.5))
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


def make_pdf(blocks, header: str | None = None) -> bytes:
    """blocks: ("h", text) | ("p", text) | ("code", text, style)
    style: mono_spaces | mono_offset (Docs export) | prop_offset (Arial) | numbered."""
    buf = io.BytesIO()
    w, h = A4
    c = canvas.Canvas(buf, pagesize=A4)
    y, page = h - TOP, 1

    def deco():
        c.setFont("Helvetica", 8)
        if header:
            c.drawString(LEFT, h - 25, header)
        c.drawString(w / 2, 20, f"Page {page}")

    def newpage():
        nonlocal y, page
        deco(); c.showPage(); page += 1; y = h - TOP

    for b in blocks:
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
                c.setFont("Helvetica-Bold" if b[0] == "h" else "Helvetica", 12 if b[0] == "h" else SIZE)
                c.drawString(LEFT, y, line)
                y -= LH + (4 if b[0] == "h" else 0)
            continue
        _, text, style = b
        font = "Helvetica" if style == "prop_offset" else "Courier"
        sp = pdfmetrics.stringWidth(" ", font, SIZE)
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
                c.drawString(LEFT + 30 + nsp * sp, y, stripped)
            else:
                c.drawString(LEFT + nsp * sp, y, stripped)
            y -= LH
    deco()
    c.save()
    return buf.getvalue()


def rasterize(pdf: bytes, dpi: int = 300) -> bytes:
    """Turn a PDF into an image-only 'scan'."""
    import pymupdf
    src = pymupdf.open(stream=pdf, filetype="pdf")
    out = pymupdf.open()
    for page in src:
        pix = page.get_pixmap(dpi=dpi)
        p = out.new_page(width=page.rect.width, height=page.rect.height)
        p.insert_image(p.rect, stream=pix.tobytes("png"))
    return out.tobytes()
