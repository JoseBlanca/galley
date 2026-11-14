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
