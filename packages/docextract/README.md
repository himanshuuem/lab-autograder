# docextract: student code from PDFs, plus a plagiarism check

Built for grading 2nd-year B.Tech programming assignments submitted as PDFs in
Google Classroom. It does two jobs:

1. **Extraction.** It turns each student PDF into runnable source files, one
   per question, plus the output the student *claims* their program printed.
2. **Similarity.** It compares every pair of students per question and shows
   suspicious pairs side by side, highlighting the matching lines.

It works on its own today, and it plugs into the autograder agent (see the
integration section below).

## What it handles

Students paste code into Google Docs or Word and export to PDF. That breaks code
in predictable ways, and each of these is repaired and **reported**:

| Problem in the PDF | What happens |
|---|---|
| Leading spaces dropped (indentation only survives as x-position) | Rebuilt from character positions. For Python, the version that compiles is chosen. |
| Code typed in Arial/Calibri instead of a monospace font | Indentation rebuilt by nesting level |
| Smart quotes `“ ”`, `‘ ’`, en/em dashes, Unicode minus, ligatures, NBSP, zero-width chars | Converted to plain ASCII |
| Auto-capitalised first word (`Int main`, `Print(`, `Def`) | Lower-cased (keywords only) |
| IDE line numbers copied along with the code | Removed |
| Page numbers, and a name/roll header repeated on every page | Removed (only in the top/bottom page margins) |
| Several questions in one PDF (`Q1`, `Ques 2:`, `Experiment No. 3`, `Program-4`, …) | Split into separate programs |
| Explanation paragraphs between code blocks | Excluded |
| `Output:` / `Sample Output` sections | Captured as `claimed_output` for the faked-output check |
| Scanned or photographed pages | Tesseract OCR, **always flagged for review** |

Languages detected: Python, C, C++ and Java. For Java, the class name is found
so the file can be saved as `ClassName.java`.

Every program carries `repairs` (what was changed), `warnings`, and
`needs_review`. A submission is never silently failed because of extraction
trouble; it is flagged for you to look at.

## Use it now, without the full stack

```bash
python3 -m venv venv && . venv/bin/activate
pip install -r requirements.txt
sudo apt install tesseract-ocr        # only needed for scanned PDFs
```

In Google Drive, open **Classroom → your course → the assignment folder**,
download it as a zip and unpack it. Then run:

```bash
python -m docextract batch "Assignment 3" --out results
# optional: --starter given_template.c   (ignore code you handed out)
#           --threshold 0.5              (similarity cut-off, 0..1)
```

You get:

- `results/extraction_report.csv`: one row per student and question, with status `OK` / `REVIEW` / `NO_CODE` / `ERROR`, warnings, and repairs
- `results/students/<name>/q1/main.c`, plus `claimed_output.txt` and `extraction.json`
- `results/similarity.csv` and `results/similarity.html`: suspicious pairs, side by side, with matching lines highlighted

For a single file:

```bash
python -m docextract extract "Alice Roy.pdf"          # print what was found
python -m docextract extract "Alice Roy.pdf" --json   # machine-readable
```

If your course uses a heading style the default pattern misses (for example
`Part (a)`), pass `--question-regex "^Part \((\w)\)"`. Group 1 is the label.

## How the similarity check works

It uses winnowing, the algorithm behind Stanford's MOSS. Code is tokenised with
comments and whitespace removed. The student's own names become `V`, numbers
become `N`, and strings become `S`. Renaming `arr` to `a`, reformatting, changing
prompts, or adding comments therefore does not hide a copy. In the tests, a fully
disguised copy scores 100% while honest solutions to the same problem score
13–32%.

Two things are ignored so that common code isn't flagged:

- the teacher's starter code (`--starter`)
- patterns shared by more than 40% of the class (`--common-frac`), such as the usual `scanf` loop

The score is shared fingerprints divided by the smaller program's fingerprints,
so a copy with extra code added still scores high. **A high score is a reason to
look, not proof.** Two students may have learned from the same textbook example.
Talk to them before acting, and follow your department's academic-integrity
process.

## Inside Lab Grader

This package is what `app/autograder/grading.py` uses to read each submission:
`extract_submission()` turns a PDF into programs per question, and
`compare_submissions()` produces the similarity pairs shown in the dashboard.

## Limits

- **OCR on code is unreliable.** Tesseract can read `1:` as `13` or `%d` as
  `%Sd`. Scanned submissions are always marked `needs_review`; check them by eye.
  Handwriting is not supported.
- Indentation is rebuilt from positions. For Python, the result is checked with
  `compile()` (which parses the code but never runs it). A remaining syntax error
  is flagged, because it may be the student's bug or an extraction problem.
- Screenshots of code pasted into the PDF are images. They are only read when
  the page has almost no real text, so a page mixing typed text and a code
  screenshot will miss the screenshot.

## Tests

```bash
python -m pytest tests -q        # 113 tests
```

The end-to-end tests generate realistic submissions in four styles (Courier with
spaces, Courier as exported by Docs, Arial, and IDE line numbers) for Python, C,
C++ and Java. Each test extracts the code, then **compiles and runs it** and checks
the real output. Separate tests cover scanned PDFs, multi-question and multi-page
PDFs, word-processor damage, a corrupt upload, an empty submission, HTML escaping
in the report, and the winnowing guarantee.
