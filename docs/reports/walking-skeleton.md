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
