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
