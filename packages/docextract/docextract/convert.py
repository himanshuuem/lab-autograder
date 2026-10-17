"""Turn whatever a student attached into one PDF for the extractor.

Supported: PDF; Word (.docx, .doc), OpenDocument, RTF, PowerPoint and Excel via LibreOffice;
images (PNG, JPEG, GIF, WEBP, BMP, TIFF, HEIC); Jupyter notebooks; ZIP archives (unpacked);
and any plain-text file, whatever its extension (.c .java .py .txt, none at all, typos like .javax).
Several attachments are merged in the order they were attached. Which pages came from
which file is recorded in the PDF's metadata (see `parts_of`), so the extractor can treat
each file as its own answer.
"""
from __future__ import annotations

import io
import json
import os
import re
import shutil
import subprocess
import tempfile
import zipfile
from dataclasses import dataclass, field

import pymupdf

MAX_FILE = 25 * 1024 * 1024
MAX_ZIP_TOTAL = 50 * 1024 * 1024     # uncompressed, per archive
MAX_ZIP_MEMBERS = 100
OFFICE_TIMEOUT_S = 120
CODE_EXT = {"c", "h", "cpp", "cc", "cxx", "hpp", "java", "py", "txt", "text", "out", "log", "in"}
OFFICE_EXT = {"docx", "doc", "odt", "rtf", "docm", "dotx",
              "pptx", "ppt", "odp", "xlsx", "xls", "ods"}
# never text, even if the bytes happen to decode
BINARY_EXT = {"exe", "dll", "so", "o", "obj", "a", "class", "jar", "pyc", "bin", "dat", "db", "sqlite",
              "mp3", "mp4", "mov", "avi", "mkv", "wav", "7z", "rar", "gz", "tar", "iso", "apk"}
JUNK_NAMES = {".ds_store", "thumbs.db", "desktop.ini"}
CAPTION = "Attached file (from Google Classroom): "   # long enough to keep a page "typed"
PARTS_TAG = "docextract-parts:"


class ConversionError(RuntimeError):
    pass


def _ext(name: str) -> str:
    base = name.rsplit("/", 1)[-1]
    return base.lower().rsplit(".", 1)[-1] if "." in base else ""


def _decode_text(data: bytes) -> str | None:
    """The text of a plain-text file in any common encoding, or None for binary data."""
    if data[:3] == b"\xef\xbb\xbf":
        data = data[3:]
    if data[:2] in (b"\xff\xfe", b"\xfe\xff"):
        try:
            text = data.decode("utf-16")
        except UnicodeDecodeError:
            return None
    else:
        if b"\x00" in data:
            return None
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            try:
                text = data.decode("cp1252")    # Windows Notepad / older editors
            except UnicodeDecodeError:
                return None
    if not text:
        return ""
    printable = sum(ch.isprintable() or ch in "\n\r\t\f" for ch in text)
    return text if printable >= 0.97 * len(text) else None


def _zip_names(data: bytes) -> list[str] | None:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            return z.namelist()
    except Exception:
        return None


def _is_notebook(data: bytes, name: str) -> bool:
    if _ext(name) != "ipynb" and not data.lstrip()[:1] == b"{":
        return False
    try:
        nb = json.loads(_decode_text(data) or "")
    except ValueError:
        return False
    return isinstance(nb, dict) and isinstance(nb.get("cells"), list) and "nbformat" in nb


def sniff(data: bytes, name: str = "") -> str | None:
    """'pdf' | 'image' | 'office' | 'zip' | 'notebook' | 'text' | None, judged by content first."""
    if data[:5] == b"%PDF-" or b"%PDF-" in data[:1024]:
        return "pdf"
    if (data[:8] == b"\x89PNG\r\n\x1a\n" or data[:3] == b"\xff\xd8\xff" or data[:6] in (b"GIF87a", b"GIF89a")
            or (data[:4] == b"RIFF" and data[8:12] == b"WEBP") or data[:2] == b"BM"
            or data[:4] in (b"II*\x00", b"MM\x00*")
            or (data[4:8] == b"ftyp" and data[8:12] in (b"heic", b"heix", b"hevc", b"heim", b"heis",
                                                         b"mif1", b"msf1", b"avif"))):
        return "image"
    ext = _ext(name)
    if data[:4] == b"PK\x03\x04":
        names = _zip_names(data) or []
        if (ext in OFFICE_EXT or any(n.startswith(("word/", "ppt/", "xl/")) for n in names)
                or b"mimetypeapplication/vnd.oasis" in data[:200]):
            return "office"
        return "zip"
    if data[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" or data[:5] == b"{\\rtf":
        return "office"
    if data[:4] == b"\xca\xfe\xba\xbe" or ext in BINARY_EXT:
        return None
    if _is_notebook(data, name):
        return "notebook"
    return "text" if _decode_text(data) is not None else None


def _heic_to_png(data: bytes) -> bytes:
    try:
        import pillow_heif
        from PIL import Image
    except ImportError:
        raise ConversionError("HEIC photos need pillow-heif, which isn't installed")
    pillow_heif.register_heif_opener()
    out = io.BytesIO()
    Image.open(io.BytesIO(data)).convert("RGB").save(out, "PNG")
    return out.getvalue()


def _image_to_pdf(data: bytes, name: str) -> bytes:
    """Put the picture on an A4 page under a one-line caption. The caption keeps
    the page 'typed', so the picture is read as a screenshot (dark terminals are
    inverted first) rather than as a scanned page."""
    if data[4:8] == b"ftyp":            # HEIC/HEIF: iPhone photos
        data = _heic_to_png(data)
    try:
        img = pymupdf.open(stream=data)
        w, h = img[0].rect.width, img[0].rect.height
    except Exception as e:
        raise ConversionError(f"{name}: not a readable image ({e})")
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((40, 40), CAPTION + name, fontsize=8, fontname="helv")
    box = pymupdf.Rect(40, 56, 555, 800)
    s = min(box.width / w, box.height / h)
    page.insert_image(pymupdf.Rect(box.x0, box.y0, box.x0 + w * s, box.y0 + h * s), stream=data)
    return doc.tobytes()


def _lines_to_pdf(lines: list[tuple[str, str]]) -> bytes:
    """Render (font, text) lines: 'helv' for labels and prose, 'cour' for code."""
    doc = pymupdf.open()
    size, lh, top, bottom = 8.5, 11, 40, 800
    # wide enough for the longest line (Courier is 0.6 em a character): text past the
    # page edge is lost when the PDF is read back. PDF pages stop at 14400 pt.
    width = min(14400, max(842, 72 + 0.6 * size * max((len(l) for _, l in lines), default=0)))
    page, y = None, bottom + 1   # forces the first page
    for font, line in lines:
        if y > bottom:
            page = doc.new_page(width=width, height=842)
            y = top
        if line.strip():
            page.insert_text((36, y), line, fontsize=size, fontname=font)
        y += lh
    return doc.tobytes()


def _text_to_pdf(data: bytes, name: str) -> bytes:
    text = _decode_text(data)
    if text is None:
        raise ConversionError(f"{name}: not a text file")
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\t", "    ")
    label = "Output:" if any(k in name.lower() for k in ("output", "out.", "result")) or _ext(name) in ("out", "log") else "Code:"
    return _lines_to_pdf([("helv", CAPTION + name), ("helv", label)] + [("cour", ln) for ln in text.split("\n")])


def _cell_text(v) -> str:
    return "".join(v) if isinstance(v, list) else str(v or "")


def _notebook_to_pdf(data: bytes, name: str) -> bytes:
    """Markdown cells become prose (so 'Q1' headings still split questions), code cells
    become code, and their saved outputs become the claimed output."""
    nb = json.loads(_decode_text(data) or "{}")
    lines: list[tuple[str, str]] = [("helv", CAPTION + name)]
    for cell in nb.get("cells", []):
        src = _cell_text(cell.get("source")).replace("\t", "    ").rstrip("\n")
        if cell.get("cell_type") == "markdown":
            lines += [("helv", re.sub(r"^\s*#+\s*", "", ln)) for ln in src.split("\n")]
        elif cell.get("cell_type") == "code" and src.strip():
            lines += [("helv", "Code:")] + [("cour", ln) for ln in src.split("\n")]
            out = []
            for o in cell.get("outputs", []):
                if o.get("output_type") == "stream":
                    out.append(_cell_text(o.get("text")))
                elif o.get("output_type") in ("execute_result", "display_data"):
                    out.append(_cell_text((o.get("data") or {}).get("text/plain")))
            out_text = "".join(x if x.endswith("\n") else x + "\n" for x in out if x).rstrip("\n")
            if out_text:
                lines += [("helv", "Output:")] + [("cour", ln) for ln in out_text.split("\n")]
    return _lines_to_pdf(lines)


def _salvage_zip(data: bytes) -> tuple[bytes | None, list[str]]:
    """Rebuild an Office file from the parts that still read correctly (an interrupted
    upload often damages the pictures but not the text). Returns (file, damaged parts)."""
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
    except Exception:
        return None, []
    good, bad = [], []
    with z:
        for n in z.namelist():
            try:
                good.append((n, z.read(n)))
            except Exception:
                bad.append(n)
    if not bad or not any(n == "[Content_Types].xml" for n, _ in good):
        return None, bad
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as out:
        for n, d in sorted(good, key=lambda x: (x[0] != "[Content_Types].xml", x[0])):
            out.writestr(n, d)
    return buf.getvalue(), bad


def _office_to_pdf(data: bytes, name: str, notes: list[str] | None = None) -> bytes:
    fixed, bad = _salvage_zip(data) if data[:4] == b"PK\x03\x04" else (None, [])
    if fixed is None:
        return _soffice(data, name)
    pdf = _soffice(fixed, name)
    pics = sum(n.startswith(("word/media/", "ppt/media/", "xl/media/")) for n in bad)
    what = f"{pics} picture(s)" if pics == len(bad) else f"{len(bad)} part(s)"
    if notes is not None:
        notes.append(f"{name}: {what} inside the file were damaged and skipped (often screenshots); "
                     "the rest was read. Ask the student to upload it again")
    return pdf


def _soffice(data: bytes, name: str) -> bytes:
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        raise ConversionError(f"{name}: Word files need LibreOffice, which isn't installed in this container")
    with tempfile.TemporaryDirectory(prefix="conv-") as d:
        src = os.path.join(d, "input." + (_ext(name) if _ext(name) in OFFICE_EXT else "docx"))
        with open(src, "wb") as f:
            f.write(data)
        # keep screenshots lossless and full resolution so their text stays readable
        export = ('pdf:writer_pdf_Export:{"UseLosslessCompression":{"type":"boolean","value":"true"},'
                  '"ReduceImageResolution":{"type":"boolean","value":"false"}}')
        if _ext(name) in ("pptx", "ppt", "odp"):
            export = "pdf:impress_pdf_Export"
        elif _ext(name) in ("xlsx", "xls", "ods"):
            export = "pdf:calc_pdf_Export"
        cmd = [soffice, "--headless", "--norestore", "--nolockcheck",
               f"-env:UserInstallation=file://{d}/profile",   # private profile: safe in parallel
               "--convert-to", export, "--outdir", d, src]
        try:
            r = subprocess.run(cmd, capture_output=True, timeout=OFFICE_TIMEOUT_S,
                               env={**os.environ, "HOME": d})
        except subprocess.TimeoutExpired:
            raise ConversionError(f"{name}: conversion took too long")
        out = os.path.join(d, "input.pdf")
        if r.returncode != 0 or not os.path.exists(out):
            raise ConversionError(f"{name}: could not convert ({r.stderr.decode(errors='replace')[:200]})")
        with open(out, "rb") as f:
            return f.read()


def _natural(s: str):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s)]


def _unzip(name: str, data: bytes) -> list[tuple[str, bytes]]:
    """The files inside an archive, in natural name order (q2 before q10). Archives
    inside the archive are returned as they are, not unpacked again."""
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
    except Exception:
        raise ConversionError(f"{name}: not a valid ZIP archive")
    with z:
        infos = [i for i in z.infolist() if not i.is_dir()
                 and not i.filename.startswith("__MACOSX/")
                 and not i.filename.rsplit("/", 1)[-1].startswith(".")
                 and i.filename.rsplit("/", 1)[-1].lower() not in JUNK_NAMES]
        if sum(i.file_size for i in infos) > MAX_ZIP_TOTAL:
            raise ConversionError(f"{name}: the archive unpacks to more than 50 MB")
        infos.sort(key=lambda i: _natural(i.filename))
        out = []
        for i in infos[:MAX_ZIP_MEMBERS]:
            if i.file_size > MAX_FILE:
                continue
            out.append((f"{name}/{i.filename}", z.read(i)))
        return out


def expand(files: list[tuple[str, bytes]]) -> list[tuple[str, bytes]]:
    """Replace each ZIP attachment by the files inside it (one level deep)."""
    out = []
    for name, data in files:
        if sniff(data, name) == "zip":
            out.extend(_unzip(name, data))
        else:
            out.append((name, data))
    return out


def to_pdf(data: bytes, name: str, notes: list[str] | None = None) -> tuple[bytes, str]:
    """Return (pdf bytes, kind). Problems that didn't stop the conversion go in `notes`."""
    if len(data) > MAX_FILE:
        raise ConversionError(f"{name}: file is larger than 25 MB")
    kind = sniff(data, name)
    if kind == "pdf":
        return data, kind
    if kind == "image":
        return _image_to_pdf(data, name), kind
    if kind == "office":
        return _office_to_pdf(data, name, notes), kind
    if kind == "notebook":
        return _notebook_to_pdf(data, name), kind
    if kind == "text":
        return _text_to_pdf(data, name), kind
    if kind == "zip":
        b = bundle([(name, data)])
        if not b.pdf:
            raise ConversionError("; ".join(b.errors) or f"{name}: the archive has no readable files")
        return b.pdf, kind
    if data[:4] == b"\xca\xfe\xba\xbe":
        raise ConversionError(f"{name}: a compiled Java .class file has no source code; "
                              "ask the student for the .java file")
    raise ConversionError(f"{name}: this file type can't be read (send PDF, Word, an image or a code file)")


@dataclass
class Bundle:
    pdf: bytes | None
    parts: list[dict] = field(default_factory=list)    # {name, kind, pages} for each file used
    errors: list[str] = field(default_factory=list)


def bundle(files: list[tuple[str, bytes]]) -> Bundle:
    """Convert every attachment (unpacking archives) and merge them, in order, into one PDF."""
    out = pymupdf.open()
    b = Bundle(pdf=None)
    flat = []
    for name, data in files:
        try:
            flat.extend(expand([(name, data)]))
        except ConversionError as e:
            b.errors.append(str(e))
    for name, data in flat:
        try:
            if "/" in name and sniff(data, name) == "zip":
                raise ConversionError(f"{name}: archives inside archives are not unpacked")
            pdf, kind = to_pdf(data, name, b.errors)
            src = pymupdf.open(stream=pdf, filetype="pdf")
            if src.needs_pass:
                raise ConversionError(f"{name}: the PDF is password-protected")
            out.insert_pdf(src)
            b.parts.append({"name": name, "kind": kind, "pages": src.page_count})
        except ConversionError as e:
            b.errors.append(str(e))
        except Exception as e:
            b.errors.append(f"{name}: {e.__class__.__name__}: {e}")
    if out.page_count:
        out.set_metadata({**(out.metadata or {}), "keywords": PARTS_TAG + json.dumps(b.parts)})
        b.pdf = out.tobytes(garbage=3, deflate=True)
    return b


def parts_of(pdf_path: str) -> list[dict] | None:
    """The {name, kind, pages} list `bundle` recorded, or None for a PDF it didn't make."""
    try:
        with pymupdf.open(pdf_path) as d:
            kw = (d.metadata or {}).get("keywords") or ""
    except Exception:
        return None
    if not kw.startswith(PARTS_TAG):
        return None
    try:
        parts = json.loads(kw[len(PARTS_TAG):])
    except ValueError:
        return None
    return parts if isinstance(parts, list) and all("pages" in p for p in parts) else None
