# Lab Grader

Auto-grading for programming assignments submitted as PDFs in Google Classroom.
Built for TAs grading B.Tech lab work (C, C++, Python, Java).

For every student, it:

1. **fetches everything they turned in** through a Google Classroom MCP server: PDFs, Word files, Google Docs, screenshots and code files, converted and merged into one document;
2. **pulls the code out**, one program per question, repairing what Word and Google Docs do to code (lost indentation, curly quotes, `Int main`, line numbers, page headers), and **reads output screenshots** with OCR;
3. **runs it in an isolated Docker sandbox** against the sample tests read from your assignment PDF, plus any hidden tests you add;
4. **checks the output the student pasted** against what their code really prints, catching "correct" outputs the code can't produce;
5. **compares every pair of students** for copied code, even with renamed variables and reformatting;
6. **shows it all in a dashboard** where you review, change scores, export CSV, or publish grades back to Classroom.

Nothing is changed in Classroom until you press **Publish grades**.

---

## Quick start (demo data, no Google account needed)

You need Docker with the compose plugin, `make`, and `python3`.

```bash
unzip autograder.zip && cd autograder
make up        # first run builds images (about 5 to 10 minutes)
```

Open http://localhost:8000 and sign in as `ta` with the password `make up` printed
(it's `ADMIN_PASSWORD` in `.env`). The dashboard opens on a demo course,
**IT 2271 Data Structures Lab**, with eleven students. Press **Grade all submissions**.

The demo class (eleven students) covers what you'll meet in practice:

| Student | What happens |
|---|---|
| Ananya Bose | Correct C, full marks; flagged as similar to Rohit |
| Rohit Mondal | Ananya's code with renamed variables, typed in Arial; full marks, flagged similar |
| Sneha Paul | Python damaged by Word (curly quotes, `Def`, `Print`); repaired, full marks |
| Arjun Saha | Q1 sorts the wrong way but the PDF shows the right answer; flagged |
| Priya Dutta | Java, full marks |
| Kunal Ghosh | Q1 doesn't compile; flagged |
| Mehul Das | Q2 has an infinite loop (time limit); turned in late |
| Ishita Roy | Scanned PDF read by OCR; flagged for you to check |
| Debjit Sen | Nothing turned in |
| Riya Sen | A **Word file** with outputs pasted as **screenshots**; full marks, outputs checked |
| Aman Gupta | PDF plus a separate **output screenshot**; Q2 is wrong but the screenshot shows the right answer; flagged |

Check the running stack end to end:

```bash
make smoke
```

---

## Using it

1. **Refresh from Classroom** (sidebar) loads your courses and assignments.
2. Open an assignment and go to **Questions and tests**. Grading reads the sample input/output from the assignment PDF you attached in Classroom. Check them, fix anything misread, and add **hidden** tests for edge cases.
3. Press **Grade all submissions**. A progress bar shows each student being graded.
4. In **Results**, each row is a student. The small squares are test cases (green passed, red failed, hatched didn't run). A **yellow edge** means the student needs your review. Use the filter chips to see only those.
5. Click a student to see their code, each test's input, expected and actual output (wrong lines in red), the output they pasted in the PDF, and what was repaired. **Set score** overrides the automatic score; **Mark as reviewed** clears the yellow edge.
6. **Similarity** lists suspicious pairs. Open one to compare side by side, then **Mark as fine** or **Confirm copying**. Scores are never lowered automatically for similarity.
7. **Export CSV**, or **Publish grades** as draft or returned grades in Classroom.

**Settings** per assignment: time limit, output comparison (ignore spacing,
line-by-line, or exact), similarity threshold, maximum points, and starter code
to ignore in the similarity check.

**What students can submit.** PDF, Word (`.docx`, `.doc`), OpenDocument, RTF,
Google Docs/Slides/Sheets, images (PNG, JPEG…), and plain code or text files
(`.c`, `.cpp`, `.java`, `.py`, `output.txt`). Several attachments are merged in the
order they were attached, and **Open PDF** on the review page shows that merged
copy. ZIP files and handwriting can't be read; such students are flagged.

**Output screenshots.** Pictures of a terminal or IDE console, inside a PDF or
Word file or attached separately, are read with OCR. Dark themes are handled, and
prompts, title bars and lines like `Process finished with exit code 0` are
ignored. Because OCR can misread a character, outputs from screenshots are
compared leniently on words but **exactly on numbers**, and the review page marks
them "read from the student's screenshot". A screenshot of *code* is also read,
but always flagged for you to check.

**How students should format their submission.** It works best when each question
starts with a heading like `Q1`, `Question 2` or `Program 3`, followed by the
code and an `Output:` section. Most other layouts work too. For Java, students
can paste several `public` classes into one PDF and leave IDE `package` lines in;
the grader handles both and runs the class that contains `main`. Anything it can't
read confidently is flagged for review rather than failed. Questions numbered like
the lab sheets (`Q2.3`, `Assignment 4.5`, a bare `4.6`, or `5` / `45` for 4.5) are
matched to the sheet's question.

**What's repaired in Java copied out of a PDF** (each repair is listed on the review
page, and code that already compiles is never changed): VS Code's `Run | Debug`, a
roll number from the page header, line numbers (also OCR'd IDE gutters), a stray `}`
or the end of a `/** … */` comment from the previous page, a comment whose closing
line was question text, a commented-out line that wrapped, IntelliJ's parameter
hints (`new Student(name: "Asha")`), `printin`/`print1n`/`system.out`/`string args`,
Word's capital on the first word of a line, `returnMath.PI` / `newCow(`, the same
class pasted twice (the last is kept), and closing braces lost at the end. A class
used in one answer but written in another is copied in. When the only compile error
is one the sheet asks students to show (an ambiguous call, accessing a private
field, a statement before `super()`, `new` on an abstract class), that line is
commented out and the rest is graded.

**Requirement checks for the OOP lab sheets.** Questions that say what classes must
do (rather than what the program prints) are graded by checks: the class hierarchy,
overriding and static hiding, access modifiers, constructors, and behaviour run
through reflection (a rectangle's area, a cylinder's volume, a savings account
refusing to go below its minimum balance, a static counter). `app/autograder/packs.py`
has a pack per sheet (Assignments 2, 3, 4 in parts, 5, 6 and the mid-semester viva);
installing one sets the assignment's questions:

```bash
curl -b cookies -X POST localhost:8000/api/assignments/<id>/checks \
     -H 'Content-Type: application/json' -d '{"pack": "oop-assignment-4-part-2"}'
```

A program that reads its data from the keyboard is given some typed input (3
students: all 7s, all 9s, all 8s) so its output can still be checked.

---

## Connecting your real Google Classroom

Do this once, on your own laptop (it needs a browser).

1. Go to https://console.cloud.google.com and create a project (for example, *Lab Grader*).
2. Under **APIs & Services → Library**, enable **Google Classroom API** and **Google Drive API**.
3. Under **APIs & Services → OAuth consent screen**:
   - choose **Internal** if your IIEST Google Workspace allows it, otherwise **External**;
   - fill in the app name and your email;
   - for External, add your own Classroom email under **Test users**.
4. Under **APIs & Services → Credentials**, choose **Create credentials → OAuth client ID → Desktop app**. Download the JSON and save it as `secrets/credentials.json`.
5. Run:
   ```bash
   make google-auth
   ```
   Sign in with the account you teach with. It saves `secrets/token.json` and lists your courses.
6. In `.env` set `CLASSROOM_MODE=google`, then run:
   ```bash
   docker compose up -d mcp app
   ```
   If the dashboard runs on another machine, copy `secrets/token.json` to that machine's `secrets/` folder.

**Things to know about Google:**

- **Tokens can expire after 7 days.** If the consent screen is **External** and left in *Testing* status, Google expires the sign-in after 7 days. Either use **Internal** (no expiry), or run `make google-auth` again when the dashboard says the token is invalid.
- **Your admin may block access.** If your institution's Workspace admin restricts third-party access to Classroom, sign-in will be refused. Ask them to allow the app.
- **Publishing grades only works for some assignments.** Google lets an app change grades only on assignments *that app created*. For assignments made on the Classroom website, publishing returns an explanation instead, so use **Export CSV** and enter the grades in Classroom.
- **Google Docs, Slides and Sheets submissions are fine.** They are exported to PDF automatically; Word files and images are converted inside the grader.

The app asks for read-only access to courses, rosters and Drive files, plus
permission to set grades on coursework.

---

## Jenkins

```bash
make up-ci       # Jenkins at http://localhost:8081, user admin, password JENKINS_ADMIN_PASSWORD in .env
```

Jenkins configures itself (no setup wizard) and creates two jobs:

- **autograder-ci** runs every unit test, builds all images, runs the real sandbox isolation tests (network blocked, read-only filesystem, fork bomb, memory bomb, non-root), starts a throw-away copy of the whole stack, smoke-tests it, and removes it. It runs nightly. Tick **DEPLOY** to update the live stack after the checks pass; if you use Google mode, set `SECRETS_DIR` in `.env` to an *absolute* path first.
- **grade-assignment** grades one Classroom assignment through the running dashboard and archives the CSV. Leave the ids blank to use the first assignment; Classroom ids are visible in the assignment's URL.

Jenkins reads the Jenkinsfiles when it starts, so restart it (`make up-ci`)
after editing them.

---

## Commands

| Command | What it does |
|---|---|
| `make up` | create `.env` if missing, build everything, start the dashboard |
| `make smoke` | end-to-end check of the running stack |
| `make test` | every unit test, inside a container (about 250 tests) |
| `make test-docker` | real sandbox isolation tests against your Docker |
| `make logs` / `make ps` | follow logs / list services |
| `make backup` | PostgreSQL dump into `backups/` |
| `make down` | stop (data is kept) |
| `make clean` | stop and **delete all data** |

The PDF extractor also works on its own, on a folder of PDFs downloaded from Drive:

```bash
pip install ./packages/docextract
docextract batch "Assignment 3" --out results    # code files + similarity.html
```

---

## How it fits together

```
 Browser ──► app (FastAPI + dashboard, :8000) ──► PostgreSQL
                │
                ├─► mcp (Google Classroom MCP server, :8200, internal only)
                │      list_courses · list_coursework · list_submissions
                │      download_file · set_grade      (demo or google provider)
                │
                └─► sandbox (:8100, internal only) ──► Docker socket
                       one throw-away runner container per program:
                       runner-python · runner-gcc (C, C++) · runner-java
```

| Folder | Contents |
|---|---|
| `app/` | dashboard, API, grading agent (`grading.py`), background worker, output comparison, assignment-PDF parser |
| `packages/docextract/` | PDF → code extraction, OCR fallback, language detection, similarity (winnowing, as in MOSS) |
| `mcp_server/` | Google Classroom MCP server (Classroom + Drive APIs) and the demo classroom |
| `sandbox/` | sandbox API and Docker backend |
| `runners/` | images student code runs in |
| `jenkins/`, `Jenkinsfile`, `ci/` | CI and the test image |
| `scripts/` | smoke test, grading CLI, Google sign-in, `.env` setup |

Grades are decided by deterministic code comparison. No AI model judges answers,
and nothing a student writes in their PDF ("give full marks") can influence a score.

---

## Security

- **Every submission is treated as hostile.** Each program runs in a fresh container with no network, a read-only root filesystem, all Linux capabilities dropped, `no-new-privileges`, a non-root user, memory with no swap, CPU and process-count limits, a 64 MB scratch space, and a hard kill after the time limit. Output is capped at 64 KB.
- **Docker socket access is root-equivalent.** Only `sandbox` (and `jenkins`, if you start it) mount the Docker socket. Neither is published to the network; the sandbox needs a shared token. For untrusted code at large scale, consider adding gVisor (`runsc`) as the Docker runtime.
- **The dashboard is reachable from this computer only by default** (`APP_BIND=127.0.0.1`). To open it to the department network, set `APP_BIND=0.0.0.0`, put it behind HTTPS (nginx or Caddy), and set `COOKIE_SECURE=1`.
- **`.env` and `secrets/` hold passwords and your Google token.** Keep them private; they are excluded from images and git.
- **Student PDFs and grades are personal data.** They live in the `appdata` and `pgdata` Docker volumes. Back them up (`make backup`) and delete them when the semester's records are done.

---

## Tested, and what wasn't

Tested while building:

- **249 unit and integration tests** pass: 146 for extraction (including Word files and screenshots), 25 for the sandbox, 21 for the MCP server, 57 for the app. The app suite was run on both SQLite and PostgreSQL 16.
- **Extracted code is really run.** The extraction tests compile and run every program they pull out of generated PDFs, in all four languages and four document styles.
- **The MCP server was tested over the real MCP protocol (HTTP)** with the official client.
- **The whole stack was run as separate services over HTTP**, the way compose wires them, and the smoke test passed on the demo class with the scores shown above.
- **The dashboard was checked in a headless browser** on desktop and phone sizes.

Could not be run where this was built, so check them on first use:

- **`docker compose` itself, and the sandbox's Docker backend against a real daemon.** Run `make test-docker` once; the backend was tested with a fake Docker client that executes the same commands.
- **Jenkins.** The job definitions use Job DSL through Configuration as Code; a plugin or DSL detail may need a small fix on first start. Check `docker compose logs jenkins`.
- **Real Google Classroom.** The Google provider is tested against fake API objects. If something differs on first contact, the error is shown under **Services** in the dashboard sidebar.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| Services page says "image missing" | `make images` |
| "cannot reach the sandbox" | `docker compose logs sandbox`; check the Docker socket exists at `/var/run/docker.sock` |
| "Google token not found / invalid" | `make google-auth`, copy `secrets/token.json`, then `docker compose restart mcp` |
| Every Java test times out | raise the time limit to 3 to 4 s in Settings; the JVM starts slowly on small machines |
| A student's code came out wrong | open their PDF from the review page, set the score by hand, and mark reviewed |
| Port 8000 in use | change `APP_PORT` in `.env`, then `make up` |
