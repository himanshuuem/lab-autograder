"""Command line.

  python -m docextract extract  submission.pdf [--out DIR] [--json]
  python -m docextract batch    submissions_dir/ --out results/ [--starter starter.c]

`batch` is meant for the folder Google Classroom keeps per assignment
(Drive > Classroom > <course> > <assignment>), downloaded as a zip and unpacked.
"""
from __future__ import annotations

import argparse
import csv
import html
import json
import re
import sys
from pathlib import Path

from .pipeline import ExtractionResult, extract_submission
from .similarity import Doc, compare_submissions

def _safe(name: str) -> str:
    return re.sub(r"[^\w.-]+", "_", name).strip("_") or "student"


def write_programs(res: ExtractionResult, out: Path) -> list[Path]:
    out.mkdir(parents=True, exist_ok=True)
    written = []
    for p in res.programs:
        qdir = out / f"q{_safe(p.question)}"
        qdir.mkdir(exist_ok=True)
        f = qdir / p.filename
        f.write_text(p.code, encoding="utf-8")
        written.append(f)
        if p.claimed_output:
            (qdir / "claimed_output.txt").write_text(p.claimed_output + "\n", encoding="utf-8")
    (out / "extraction.json").write_text(json.dumps(res.to_dict(), indent=2), encoding="utf-8")
    return written


def cmd_extract(a) -> int:
    res = extract_submission(a.pdf, ocr=a.ocr, question_re=a.question_regex)
    if a.json:
        print(json.dumps(res.to_dict(), indent=2))
    else:
        for p in res.programs:
            flag = "  [REVIEW]" if p.needs_review else ""
            print(f"=== Question {p.question} ({p.language or '?'}){flag}")
            print(p.code)
            if p.claimed_output:
                print(f"--- claimed output\n{p.claimed_output}")
            for w in p.warnings:
                print(f"! {w}")
            if p.repairs:
                print(f"~ repairs: {p.repairs}")
            print()
        for w in res.warnings:
            print(f"! {w}")
        if res.repairs:
            print(f"~ document repairs: {res.repairs}")
    if a.out:
        write_programs(res, Path(a.out))
    return 0


def _report_html(pairs, docs_by_q, out: Path) -> None:
    def code_html(code: str, spans) -> str:
        hit = {n for a, b in spans for n in range(a, b + 1)}
        rows = []
        for i, line in enumerate(code.split("\n"), 1):
            cls = ' class="hit"' if i in hit else ""
            rows.append(f'<span{cls}><i>{i:>3}</i> {html.escape(line)}</span>')
        return "<pre>" + "\n".join(rows) + "</pre>"

    parts = ["""<!doctype html><meta charset="utf-8"><title>Similarity report</title>
<style>body{font:14px system-ui,sans-serif;margin:24px;max-width:1300px}
.pair{border:1px solid #ccc;border-radius:8px;margin:16px 0;padding:12px}
.cols{display:grid;grid-template-columns:1fr 1fr;gap:12px}
pre{background:#f7f7f7;padding:8px;overflow-x:auto;font-size:12px;line-height:1.35}
.hit{background:#ffe08a;display:inline-block;width:100%}i{color:#999;font-style:normal}
.note{color:#555}</style>
<h1>Code similarity report</h1>
<p class="note">Highlighted lines share structure after renaming variables and removing
comments. Patterns most of the class shares are ignored. A high score is a reason to
look, not proof of copying: talk to the students before acting.</p>"""]
    if not pairs:
        parts.append("<p>No pairs above the threshold.</p>")
    for q, pr in pairs:
        docs = docs_by_q[q]
        parts.append(f'<div class="pair"><h3>Q{html.escape(q)}: {html.escape(pr.a)} vs '
                     f'{html.escape(pr.b)} - {pr.score:.0%} '
                     f'{"(short program, low confidence)" if pr.low_confidence else ""}</h3>'
                     f'<div class="cols"><div><b>{html.escape(pr.a)}</b>'
                     f'{code_html(docs[pr.a].code, pr.lines_a)}</div>'
                     f'<div><b>{html.escape(pr.b)}</b>{code_html(docs[pr.b].code, pr.lines_b)}</div></div></div>')
    out.write_text("\n".join(parts), encoding="utf-8")


def cmd_batch(a) -> int:
    src, out = Path(a.folder), Path(a.out)
    pdfs = sorted(p for p in src.rglob("*") if p.suffix.lower() == ".pdf")
    if not pdfs:
        print(f"no PDFs found in {src}", file=sys.stderr)
        return 1
    out.mkdir(parents=True, exist_ok=True)
    starter = Path(a.starter).read_text() if a.starter else None
    docs_by_q: dict[str, dict[str, Doc]] = {}
    rows = []
    for pdf in pdfs:
        student = pdf.stem
        try:
            res = extract_submission(str(pdf), ocr=a.ocr, question_re=a.question_regex)
        except Exception as e:
            rows.append({"student": student, "question": "", "language": "", "status": "ERROR",
                         "needs_review": True, "warnings": str(e), "repairs": ""})
            print(f"  {student}: ERROR {e}")
            continue
        write_programs(res, out / "students" / _safe(student))
        if not res.programs:
            rows.append({"student": student, "question": "", "language": "", "status": "NO_CODE",
                         "needs_review": True, "warnings": "; ".join(res.warnings), "repairs": ""})
        for p in res.programs:
            docs_by_q.setdefault(p.question, {})[student] = Doc(student, p.code, p.language)
            rows.append({"student": student, "question": p.question, "language": p.language or "?",
                         "status": "REVIEW" if p.needs_review else "OK",
                         "needs_review": p.needs_review,
                         "warnings": "; ".join(p.warnings + res.warnings),
                         "repairs": ", ".join(f"{k}={v}" for k, v in {**res.repairs, **p.repairs}.items())})
        print(f"  {student}: {len(res.programs)} program(s){' [REVIEW]' if res.needs_review else ''}")

    with open(out / "extraction_report.csv", "w", newline="", encoding="utf-8") as f:
        wr = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        wr.writeheader()
        wr.writerows(rows)

    all_pairs = []
    for q, docs in sorted(docs_by_q.items(), key=lambda kv: int(kv[0]) if kv[0].isdigit() else 0):
        for pr in compare_submissions(list(docs.values()), starter_code=starter,
                                      threshold=a.threshold, common_frac=a.common_frac):
            all_pairs.append((q, pr))
    all_pairs.sort(key=lambda t: -t[1].score)
    with open(out / "similarity.csv", "w", newline="", encoding="utf-8") as f:
        wr = csv.writer(f)
        wr.writerow(["question", "student_a", "student_b", "score", "jaccard", "shared", "low_confidence"])
        for q, pr in all_pairs:
            wr.writerow([q, pr.a, pr.b, pr.score, pr.jaccard, pr.shared, pr.low_confidence])
    _report_html(all_pairs, docs_by_q, out / "similarity.html")

    n_rev = sum(1 for r in rows if r["needs_review"])
    print(f"\n{len(pdfs)} PDFs, {n_rev} row(s) need review, {len(all_pairs)} similar pair(s).")
    print(f"See {out/'extraction_report.csv'} and {out/'similarity.html'}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="docextract")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("extract", "batch"):
        p = sub.add_parser(name)
        if name == "extract":
            p.add_argument("pdf")
            p.add_argument("--json", action="store_true")
            p.add_argument("--out")
        else:
            p.add_argument("folder")
            p.add_argument("--out", required=True)
            p.add_argument("--starter", help="teacher's starter code to ignore")
            p.add_argument("--threshold", type=float, default=0.5)
            p.add_argument("--common-frac", type=float, default=0.4,
                           help="ignore patterns shared by more than this fraction of the class")
        p.add_argument("--ocr", choices=["auto", "always", "never"], default="auto")
        p.add_argument("--question-regex", help="custom regex for question headings; group 1 = number")
    a = ap.parse_args(argv)
    return cmd_extract(a) if a.cmd == "extract" else cmd_batch(a)
