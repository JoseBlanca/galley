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

### Review of work package 1

Four reviewers (spec, tests, fidelity, conventions) on 6d201b1..0040fc3.
Every finding held; all were fixed (9c2eaca specs, then cb78d74,
408e5dc, f99eb48, 52d0a9f). What mattered:

- **The fidelity check could let a word hide or be invented** once
  work package 2 makes reference spans: a one-letter span ("à", "a")
  passed as a marker and vanished at markdown (Mariéjol has 18,247 block
  words of that shape); the text of an endnote link was never compared;
  the reference rules ran only at structure. Decided by the orchestrator,
  as a stricter check (architecture §13, reversible by reverting
  9c2eaca and cb78d74): a letter is allowed in a span only with a round
  bracket ("(t)", "U)"); "&" and dashes are refused; an endnote link's
  text is counted on both sides; the reference rules run at markdown too.
- **Tests that could not fail**: a dropped endnote link went unreported
  by any test; the pitch, median, row-top and 2 pt edge-window rules of
  `body_measures` and two thresholds survived mutation. Each now has a
  test that fails when broken.
- **Conventions**: the word list is lowered in one place (analyze would
  otherwise have missed 72% of the English list); layout's leftover copy
  of the edge count and its second name for the row rule are gone; the
  error for a version-1 `blocks.json` says to rerun structure.
- **Configs**: Gierke's "Analytical summary" (pages 52–60) and its
  list of the notes' subjects (61–67) repeat the section headings, so
  `contents_pages` is now [10, 52–67] (decided by the orchestrator, by
  the owner's rule that the table of contents lists no chapter twice).
  A page in both `plate_pages` and `exclude_pages` is excluded
  (architecture §6).

After the fixes, at 52d0a9f: pytest 1175 passed in 27.0 s; with 8
threads in 50.4 s; `-m whole_book` 22 passed in 85.3 s; ruff, ty and
`uv lock --check` pass.

Work package 1 is done.

## Stream `markdown`: tasks 7.1 and 7.2 (5b57b62, 9b1ebd7, merged)

markdown writes every kind, each by what it is (described in the
markdown stage's docstring, "How each kind is written"):

- a heading is a Pandoc heading with its label as a `.label` span;
- the other kinds are divs with a class (`quote`, `chapter-summary`,
  `index-entry`, `figure`, `margin-note`);
- verse has a hard break at each line end;
- a referenced footnote is a Pandoc footnote holding its margin notes;
- an endnote is an `.endnote` div where it was printed, reached by an
  `epub:type="noteref"` link.

Deliverable 1: 36 tests collected; deliverable 2: the hand-made EPUB
passes epubcheck, with the noteref link and `<br />` in the verse.
markdown now also refuses, as malformed, a reference naming no note, a
note whose `referenced` disagrees with its references, a footnote
referenced twice, and a footnote reference inside a footnote.

Left open: a figure's image is not yet written, because the fidelity
check refuses Pandoc's Image and Figure elements; that change to
`fidelity.py`, a shared file, is made on the plan's branch after the
`plates` stream merges, before task 6.3. Endnote divs carry no
`epub:type="endnote"`, which some readers hide from the reading flow;
the pop-ups have not been tried on a Kindle.

The default pytest run took 39.5–40.9 s while three streams ran (load
average 11–12); it is measured again when the machine is idle.

## Stream `layout`: task 3.1 (b1107d0, merged)

layout measures the cut-in inset on each side (`BookMeasures`
`cut_in_inset_left`, `cut_in_inset_right`) and runs step 2b; the note
words form margin regions of their own. 18 tests (`-k cut_in`), each
threshold broken once and a test failing. Of the 11 excerpts only
`stubbs_51_56-64` gets insets (60.3 and 58.2 pt); the nearest miss is
`mariejol_headings_verse`, 14 rows at 73.8 pt against 6 beside it.

Whole Stubbs: 1,324 words moved on 216 pages (the spec measured 1,314;
the 10-word gap was not found), insets 60.3 pt (397 rows) and 59.3 pt
(362). No other book gets an inset. The inset peak is tried only at the
insets rows have, which the spec did not say; trying every 0.1 pt gave
the Mariéjol excerpt a false inset.

Three Stubbs reference pages changed, checked by the orchestrator
against the excerpt text: page 0, "accession." leaves the body line as
a margin note; page 9, the notes "Banishment of mercenaries." and
"Destruction of castles." (OCR "B an i s h m e n t", "Cti°n °£ J^tE.")
leave the body, and "fifteen, was a still greater boon ; for these,"
is one line again; pages 4–5, the note "Henry's mismanagement of his
children." becomes a margin note, joined at its hyphen as a guess
("Silmlnagementofhis", the OCR's text). They go into the owner's sheet
of task 7.3.
