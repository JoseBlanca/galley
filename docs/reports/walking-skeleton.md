# Report: the walking skeleton

The work report of `docs/plans/walking-skeleton.md`, written while the plan
runs, for the owner. Started on 14 November 2026 on branch
`plan/walking-skeleton`, from `main` at e60d2f3.

## Before the first task

Prerequisites, checked in the plan's worktree on 14 November 2026:

- Pandoc is 3.14, not the 3.13 the plan named: Homebrew upgraded it when
  epubcheck was installed. The behaviours the spec relies on were checked
  again on 3.14 and hold: one chapter file per level-1 heading with the
  block ids kept as `div` ids; note blocks keep their ids inside the
  footnote `aside`; a link to `#b-p0000-002` from another chapter becomes
  `ch001.xhtml#b-p0000-002`; with `-f markdown-smart`, `"quotes"` and `--`
  are read back unchanged; an unused note definition with
  `--fail-if-warnings` exits with 3; a reference with no definition is
  printed as text, `Text.[^zz]`, with exit 0. The plan's prerequisite now
  names 3.14.
- `uv run --locked pytest`: 5 passed.
- `uv.lock`: pdfplumber 0.11.10, pypdfium2 5.15.2.
- epubcheck: `/opt/homebrew/bin/epubcheck`, EPUBCheck v5.4.0.
- The whole books are in `samples/public_domain/` of the main checkout
  (4,830,323 and 24,281,471 bytes).
- No other session's worktree exists, so the board was not used.

## Work package 1: the data formats

One stream, `formats`, one subagent, four commits (488444c, e14f23b,
56dcd16, 889d220), merged into the plan's branch as fad593c.

Deliverables, checked by the orchestrator on fad593c's stream branch:

| deliverable | command | result |
|---|---|---|
| 1. error classes | `pytest tests/test_errors.py --collect-only -q` | 7 tests (at least 2) |
| 2. formats | `pytest tests/test_model.py --collect-only -q` | 80 tests (at least 24) |
| 3. config | `pytest tests/test_config.py --collect-only -q` | 43 tests (at least 16) |
| 4. book folder | `pytest tests/test_book_folder.py --collect-only -q` | 1 test (at least 1) |
| 5. imports | `python -c "import galley.errors, galley.model, galley.config, galley.book_folder"` | exit 0 |

The six checks of the coding skill pass: `uv run --locked pytest`, 136
passed, 0 skipped, in 0.23 s; with `--parallel-threads=8`, 136 passed in
0.98 s.

What the stream did beyond the plan, each checked against the spec:

- `RemovalReason.plate_text` is in the enum, as architecture §8 names it.
- `Edit.format_version` is the first field, default 1, so that it is first
  on every line of an edits file.
- The readers also reject text that is not UTF-8 and a top level that is
  not a JSON object; `read_edits` rejects unknown and wrongly typed fields.
- Every float field is written as a float, so a box of ints and the same
  box of floats give the same bytes, as spec §3's byte-identity rule asks.
- ty 0.0.104 checks `frozendict` without complaint; no format needed
  `sentinel`.

### Review of work package 1

Four reviewers (spec, tests, fidelity, conventions) on fad593c. Every real
word of both excerpts (9,527) and 27 hard texts (combining accents, long
s, ligatures, bidirectional marks, zero-width characters, emoji, control
characters) came back from the formats unchanged. Findings that held,
fixed by the stream's agent test first in 12 commits (39bd97b to
adb3d4f), the spec's section 3 first:

- A word holding a lone surrogate made a writer crash after emptying the
  file it was replacing. Files are now written whole or not at all (a
  temporary file renamed over the old one), and readers refuse such text.
- Readers accepted NaN and infinity as numbers, and the config accepted
  them in a region's box, where NaN made the region exclude nothing in
  silence. Refused now, and never written.
- A JSON key given twice was read as its last value; an edits file that
  is not UTF-8 gave Python's decoding error without the file's name.
  Both are errors naming the file now.
- The architecture promises how a `frozendict` is written; the reader
  could not read it back. Done, though no field uses one yet.
- Tests that could not fail: 8 of 22 deliberate breaks of the code passed
  the whole suite, and 11 enum spellings of the formats were pinned by no
  test. Each now has a test that fails when the code breaks.
- Small spec changes decided by the orchestrator (no format or EPUB
  change): the fidelity boundary is an enum, `FidelityBoundary`, in
  `errors.py`; `check_source_pdf`'s parameter is `expected_pdf_sha256`;
  an empty title or author list is an error; the PDF path is always
  resolved; -0.0 is written as 0.0.

Not taken: sorting the words in a fidelity error's message stays; the
small type-check helpers stay duplicated in `config.py` and `model.py`,
because they raise different errors.

After the fixes: the six checks pass, 185 tests, none skipped, 0.28 s
(1.13 s with 8 threads).

For the next work package: pdfminer, under pdfplumber, decodes some text
with `errors="ignore"` and can drop a broken character before galley
sees it (`pdfminer/cmapdb.py`, line 190). That is for extract's spec.

## Work package 2: shared machinery

Two streams side by side, each in its own worktree, merged into the
plan's branch: `fidelity` (e1a6de2, 1685562, f218d16; merge 9373fe8) and
`pdfium` (a26d5c2, 664c710, 0970fdf, d430f89; merge 9b3458f). The two
streams edited different sections of the spec and merged without
conflict.

Deliverables, checked by the orchestrator:

| deliverable | command | result |
|---|---|---|
| 1. PDFium in one thread | `pytest tests/test_pdfium.py --collect-only -q`; with `-m thread_unsafe` | 20 tests (at least 7); 15 thread_unsafe (at least 6) |
| 2. the pool | `pytest tests/test_parallel.py --collect-only -q` | 22 tests (at least 6) |
| 3. the word check | `pytest tests/test_fidelity.py -m "not pandoc"` | 15 passed (at least 11) |
| 4. reading the Markdown | `pytest tests/test_fidelity.py -m pandoc -rs` | 11 passed, none skipped (at least 7), Pandoc 3.14 |

After both merges the six checks pass: 253 tests, none skipped, 2.84 s
(3.88 s with 8 threads).

Spec changes the streams made before their code, each in a commit of its
own:

- Kadesh's page size as pypdfium2 gives it is 508.29998779296875 pt wide,
  not 508.32 as the spec said: PDFium clips the crop box to the media box.
  No stage calls `page_size`; page sizes in the files are pdfplumber's.
- `strip_stride` refuses a buffer that does not fit its shape;
  `map_pages_with_source` says which error it raises when two kinds happen.
- The fidelity check: when only the note counts differ, the error gives
  both counts; a removal's text is split into words; `read_markdown`
  accepts only the Pandoc elements galley writes and stops on any other,
  so that a list or a table made by a missing escape cannot drop words.

Every PDFium object is closed in the PDFium thread: a test reads
pypdfium2's log of closes (4 documents, 1 page, 1 bitmap closed
explicitly, none by a finalizer), and another finds pypdfium2 running in
one thread only; with the calls moved to the caller's thread, the test
process crashed inside PDFium.

Question for the review: `parallel.py` keeps a small mutable record per
worker to find the first failing item without a `try`, against the
coding skill's functional style.

### Review of work package 2

Four reviewers on 9b3458f. Building Markdown from every word of both
excerpts, escaped as spec §8 says, and reading it back through
`read_markdown` with Pandoc 3.14 gave 6,121 of 6,121 and 3,406 of 3,406
words; one changed letter, a duplicate, a lost word, an added accent and
an added zero-width space were each caught. The tests reviewer broke the
code 50 ways: results in input order, every PDFium object closed
explicitly, and note references counted as words of their own are
guarded.

Findings that held, fixed in two fix branches side by side (pdfium-fix:
639e656, f22af19, 620f3d9; fidelity-fix: 7fe30db to d1c1f2f), the spec
first in each:

- Two holes in the fidelity check itself: a note reference span could
  carry a body word away (counted at structure, never at markdown), and a
  recorded word change was trusted whatever it said ("Greece" to "Greek"
  as a hyphen join passed). A reference span must now be exactly its
  note's marker, and each word change is checked by its reason.
- A word invented in `book.md`, and a word duplicated at structure or
  markdown, could pass without any test failing; tests added.
- Words with white space inside were split on one side only; Pandoc's
  automatic heading ids could name a block not in `book.md`; the Pandoc
  call is now apart from the pure walk of its JSON.
- The only guard against an item lost by the pool was an `assert`, which
  `python -O` removes; an explicit check now. A missing PDF and a dpi
  below 1 give errors that name them. The order tests now really use
  several threads (they had run on one), and a test pins which error wins
  when two workers fail.

Kept on the reviewers' evidence: `parallel.py`'s per-worker record, written
only by its worker and read after the join (300 rounds with the GIL off,
the right failure every time). The coding skill now allows that pattern
(55d1104).

After the fixes: 284 tests, none skipped, 2.88 s (4.44 s with 8 threads).

For work package 3: Pandoc drops a carriage return inside a word (`ab\rcd`
becomes `abcd`) and reads a leading tab as a code block, so the markdown
stage's escaping must handle C0 white space.

### How the work went (for whoever next revises a skill or writes a plan)

- Each coding agent's report was right about what it built; every
  review still found real defects, most of them in tests that could not
  fail (8 of 22 mutations survived in work package 1, several in work
  package 2). A mutation pass by the tests reviewer is worth its cost.
- Tokens, from the Agent results: work package 1, coding 153k, four
  reviews 255k, fixes 226k; work package 2, coding 243k (two streams),
  four reviews 256k, fixes 303k. A work package costs about three times
  its coding.

## Work package 3: the six stages in their simplest form

Three streams side by side, merged one after the other into the plan's
branch: `structure` (1b3683e, e97e395, b2839ac; merge d15b872), `epub`
(9cfe285, 5825ec8, 3e2a4af; merge d227e26) and `extract` (4b9b738,
346b4bd, 5fdc2ca; merge 9782bab). Each changed only its own section of
the spec, so the three merged without conflict.

Deliverables, checked by the orchestrator on 9782bab:

| deliverable | result |
|---|---|
| 1. analyze | 16 tests (at least 8) |
| 2. extract | 25 tests (at least 4) |
| 3. analyze and extract on the excerpts | every count, box and opening word of spec §2 and §6 matched; the Kadesh cover is 2118 × 3034 pixels, 2,358,031 bytes |
| 4. their own runs | 7 thread_unsafe tests, among them 1 against 6 workers byte for byte |
| 5. layout | 16 tests (at least 10); the line rule gives spec §2's 387 lines on Kadesh and 366 on Gierke |
| 6. structure | 9 tests (at least 4) |
| 7. markdown | 19 passed, none skipped (at least 9) |
| 8. epub | 5 passed, none skipped (at least 4) |
| 9. `style.css` in the package | `True`; also in the wheel |
| 10. every stage's `run` | the import command exits 0 |
| 11. a hand-written EPUB passes epubcheck | 1 passed; epubcheck fails on a copy without its language, so the test can fail |

The six checks pass: 375 tests, none skipped, 8.23 s (8.95 s wall time);
with 8 threads 10.89 s. Both under the 30 s budget.

Choices the streams wrote into the spec, each before its code:

- layout and structure check `pages.json` against the PDF's own hash as
  well as their input against `pages.json` (0.4 ms on Kadesh), so that a
  stale `pages.json` names analyze. Accepted by the orchestrator.
- markdown turns tabs, line feeds and carriage returns into spaces and
  trims them at the ends of a text: Pandoc 3.14 drops a carriage return
  inside a word and reads a leading tab or four spaces as a code block.
  Tested through Pandoc on 258 texts; all 55 C0 and C1 control characters
  otherwise come back unchanged.
- extract refuses a `pages.json` that holds a plate page or a page marked
  for OCR, which the skeleton cannot read, rather than drop its words.

For the extract stage's spec: Pandoc writes control characters such as
NUL into the EPUB's pages, where XHTML forbids them; no word is lost, but
the EPUB would fail epubcheck. What such characters become is extract's
decision, with the pdfminer finding of work package 1.
