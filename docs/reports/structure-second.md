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

### Task 1.2 (baaa226, merged)

`body_measures.py` holds the row grouping, the commonest edge, the word
height and pitch, used by layout and structure; their copies and the
test that compared them are gone. `wordlist.word_key` and
`is_known_word` are shared. The six excerpts' `lines.json` and
`blocks.json` are byte-for-byte the same before and after. pytest on the
plan's branch after the merge: 1133 passed in 28.0 s, close to the
coding skill's 30 s budget before the five new excerpts.

### Tasks 1.3 and 1.4 (d63b0b4, 43c4e4b, merged; then 3eecabd, 63957e8)

The five new excerpts are cut by `scripts/fetch_samples.py`, committed,
and in `EXCERPT_CONFIGS`. The six books' configs live in
`WHOLE_BOOK_CONFIGS` of `tests/conftest.py`, used by every whole-book
test, and in `evaluation/books.toml`; a default-run test checks that the
two agree. galley-eval passes `contents_pages` and `plate_pages` on, and
`docs/specs/evaluation.md` §3 lists them.

Changed from the plan: the five new excerpts took the default run to
29.6–30.4 s. The plan's fallback, a fixture of their own, would not have
saved time, so the shared fixture now runs the excerpts six at a time in
threads (setup 7.5–8.1 s → 4.4–4.6 s), with byte-identical outputs apart
from the EPUB's identifier and date. Kadesh's `plate_pages = [23]` is
written, and page 23 stays in `exclude_pages` until task 6.1.

### Deliverables of work package 1, at 63957e8

1. The version assert passes; `-k "label or note_kind …"` on
   `tests/test_model.py` collects 9.
2. `tests/test_fidelity.py -k "label or endnote"` collects 11.
3. `-k "contents_pages or plate_pages"` on config and analyze collects 10.
4. `import galley.body_measures` passes; the grep for the old copies
   prints nothing.
5. `tests/test_wordlist.py -k known_word` collects 9.
6. The grep for the five excerpts in `tests/test_excerpts.py` gives 10.
7. `grep -c contents_pages evaluation/books.toml` gives 4; `-m
   whole_book`: 22 passed in 84.7 s.
8. Default pytest: 1152 passed in 27.2 s; with 8 threads in 50.7 s.
