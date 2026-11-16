# Report: structure, the second part

The work report of the plan `docs/plans/structure-second.md`, written as
the work goes, for the owner. Started 16 November 2026, on branch
`plan/structure-second`, made from `spec/structure-2`.

## Before the first task

- The tools are in place: `which pandoc tesseract combine_tessdata
  dawg2wordlist epubcheck` prints five paths; `tesseract --list-langs`
  lists `eng` and `fra`.
- `uv run --locked pytest`: 1049 passed, 16 deselected, in 24.5 s.
- The baseline: `uv run galley-eval run` at 9091e32, copied to
  `runs/structure-second-baseline/` of the main checkout.
- No other session is working, so the board was skipped.

## Work package 1, Foundations

### Task 1.1 (b55ea26, with spec commits 8e4c988 and 536cea8)

`blocks.json` is at version 2, with `Block.label`, `Note.kind`
(`NoteKind`: footnote, endnote), `BlockKind.verse` and
`chapter_summary`, `RemovalReason.guide_words`; config keys
`plate_pages` and `contents_pages`, checked by analyze; the fidelity
rules for labels, reference spans of a marker's shape, and endnote
markers. pytest: 1110 passed in 23.9 s; with 8 threads in 43.2 s.

Beyond the task: architecture §13 did not say how the fidelity check
reads a link to an endnote, and the markdown stream may not change
`fidelity.py`, so task 1.1 settled it (8e4c988): `read_markdown` counts
links marked `epub:type="noteref"` and refuses any other link. The
evaluation tool learnt the two new kinds so that it still reads
`blocks.json`; which reference kinds they match stays task 7.4's.
