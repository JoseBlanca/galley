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
a margin note; page 9, the notes "Banishment of mercenaries." and the one
the OCR reads "Cti°n °£ J^tE." (the first read "B an i s h m e n t")
leave the body, and "fifteen, was a still greater boon ; for these,"
is one line again; pages 4–5, the note "Henry's mismanagement of his
children." becomes a margin note, joined at its hyphen as a guess
("Silmlnagementofhis", the OCR's text). They go into the owner's sheet
of task 7.3.

## Stream `plates`: tasks 6.1 and 6.2 (42eed95, 003b6aa, merged)

analyze renders each page at 36 dpi in the PDFium thread and applies
plates §2's rule in the workers; `plate_pages` forces a plate,
`exclude_pages` wins; each page taken is logged at WARNING and is exempt
from the blank-page refusal. extract renders each plate at 300 dpi to
`images/plate-NNNN.png`, gives the page one whole-page figure, and reads
its text layer. The plates without a text layer (Kadesh 17, 23, 35, 43,
57, 69; Stubbs 9, 11, 52, 54) are out of `exclude_pages`.

On the six books analyze takes exactly the 22 plates of plates §1 and
nothing else: Kadesh 16, 17, 19, 22, 23 (by `plate_pages`), 24, 34, 35,
42, 43, 48, 56, 57, 64, 68, 69; Domesday 39, 40; Stubbs 9, 11, 52, 54.
Domesday's analyze takes 14.3 s against 4.3 s before; the renders are
14.5 s of it (the spec measured 12.6 s). `-m whole_book`: 28 passed in
243 s (under load).

6.2 was committed before 6.1: once analyze takes plates, extract's old
refusal broke every excerpt run. The stream needed one file outside its
list, `tests/test_end_to_end.py` (Kadesh's excerpt now has two plate
images); the orchestrator added it to the stream's files.

## Figure images in markdown (eda92f2 spec, 5c2380e code)

The open point of the `markdown` stream, made on the plan's branch: a
figure is a div of class `figure` holding only its image, the caption as
the image's text (`![PLATE I\. The battle\.](images/plate-0016.png)`).
The fidelity check (architecture §13) counts the caption's words once,
requires the alt text to equal the caption (or be empty with no
caption) and title and attributes to be empty, and refuses every other
Image or Figure. epub passes the book folder to Pandoc as its resource
path. A test EPUB with a captioned and an uncaptioned figure passes
epubcheck.

**The test budget.** The default run took 41.1 s at load average 5.7
(the `notes` stream running), against the coding skill's 30 s. The
slowest parts: the excerpt fixture's setup, 5.5 s (now with plate
renders), and seven tests of about 1.6–2.2 s each, five of them
epubcheck runs. Added to the plan: after the `notes` stream merges, the
run is measured on an idle machine, and if it is over 30 s a task brings
it back under (before work package 2's review).

## Stream `notes`: work package 2, tasks 2.1 to 2.5 (merged at 19703a4)

Commits: 3505c33 and 81ecd6d (spec), ab4869f (2.1), c30cc61 (2.2),
1bb0fa8 (2.3), dbfdad7 (2.4), b604dba (2.5). The band is cut into notes
by structure §11's start rules, markers are taken off, notes over a page
break are joined, notes left at the foot of the body are taken,
references are found and linked, Gierke's endnote section is read, and a
margin note beside a note's line goes inside that note.

Whole books, 16 November 2026:

| book | footnotes linked | joined over a page break | taken from the body |
|---|---|---|---|
| Haskins | 63 of 72 | – | – |
| Domesday | 1,489 of 1,731 | 48 | 42 notes on 15 pages |
| Mariéjol | 651 of 1,141 | 25 | 147 notes on 44 pages |
| Kadesh | 31 of 149 | 4 | – |
| Stubbs | 0 of 163 (its index and lists; 164 and 5 after the layout merge) | 6 | – |

Gierke: 299 endnotes, from page 186 (the last runs on to the library card on page 288, a fault the review found), 213 linked (the spec's
prototype linked 205). "Linked" here is the stage's own count; whether
each link is right is scored in task 7.5.

Decided by the orchestrator during the stream, each written into
structure §11 before the code (3505c33, 81ecd6d):

- a band line starts a note under rule 1 only when indented after a
  short line, not when it is only centred; a page's single band line is
  never indented;
- the first line of a later column of a band starts a note when it is
  indented against that column (Kadesh page 8, the right column);
- a reference candidate has punctuation before its digits or is glued to
  a word; a bare "13," is not (Kadesh page 10); punctuation means
  Unicode's punctuation categories, so "£2" is not a reference
  (Domesday page 83);
- a page's first note with no marker, not indented and joining no
  earlier note is not counted in the per-page numbering (Mariéjol page
  211);
- a reference that was a whole word with a letter is not linked, as
  architecture §13 now requires. This leaves Mariéjol's "(i)." (the
  OCR's "(1).") unlinked.

The stream twice needed files outside its list (`tests/test_end_to_end.py`,
the structure spec); the orchestrator added them.

Reference pages changed, each with its "changed" sentence, checked by
the orchestrator against the page image or the excerpt's text: Domesday
74, 75, 76 and 83 (the eight notes of 83 against the image), Haskins
132, Kadesh 8 and 10, Mariéjol 214, Gierke 270. They go into the
owner's sheet of task 7.3.

Open, for the review: Kadesh's marker form comes out as "sign", not the
digits structure §1 states, and only 31 of its 149 notes are linked,
against 42 in the spec's research.

After the merge: pytest 1370 passed in 34.2 s at load average 3.3;
`-m whole_book` 28 passed in 232 s.

## Review of work package 2 and the merged streams (75cc16b..cfe6c17)

Four reviewers. The fidelity reviewer ran all six books through markdown:
the fidelity check passed at every stage, every block's words reach
`book.md`, and none fall outside a block. What mattered, all taken:

- **Gierke's endnotes 1–7 were linked from Maitland's introduction**,
  whose footnote references won the match; Gierke's own "Law1" (page 88)
  and five others stayed unlinked: 7 wrong pop-ups, 6 missing. Decided:
  endnote references are looked for only after the book's last contents
  page.
- **Gierke's library card (page 288) was inside endnote 345**, the last
  endnote running over the blank pages 283–287. The report's page range
  above was wrong; corrected.
- **Stubbs' step 2b moved words out of a sentence**: "as his" on page
  33, three page numbers of an index entry on page 317. Decided: a word
  less than 5 pt from a body word of its row stays. This is part of the
  cost of the 0.913 precision the owner accepted.
- **The endnote section's rules were untested**: removing its rising
  order passed every test and, on Gierke, made 304 endnotes with 13
  linked. Tests on the excerpt and a whole-book test are being added,
  with one test each for about twenty other rules that survived
  mutation.
- **Mariéjol: a reference with a letter is dropped before matching**,
  where the spec drops it after; 23 links differ. To be scored against
  the reference text, and the better order kept.
- **The excerpt `domesday_headings_quotes` has no footnote band** (body
  height 9.0 against the book's 10.0), so it cannot test what structure
  §9 names it for; task 4.0 re-cuts it.
- **Kadesh**: the code is right; structure §1 was wrong to call its
  marker form digits (24 sign, 14 digits). Its 31 links of 149 follow
  from markers that are signs with no value.
- Also: the note placement rule was written in structure and markdown
  (to one function in `model.py`); a one-letter word taken as a note's
  marker is guarded; a hyphen split by a reference (Haskins page 71) is
  joined; a missing figure image gets galley's own error; `_assemble.py`
  is split.

Not taken now: older guessed joins that make compounds of real
hyphenated words ("sixteenhundredth", "PLANTAGENETSCHAPTER"), for the
correct stage; a footnote joining over a plate page, for task 6.3.

The fixes run in two worktrees, structure (`fix-s`) and the other stages
(`fix-l`).

### The fixes (merged: fix-l at 97b8f32, fix-s at 934befa)

- **Stubbs' step 2b** (e87ec43): a word less than 5 pt from a body word
  of its row stays. Whole Stubbs: 1,318 words moved (1,324 before);
  "as his" (page 33) and "255, 266, 274" (page 317) stay in their
  sentences; the cost is one note word, "heBarons" on page 226 (the
  OCR's "the Barons.", checked on the image). Precision with today's
  evaluation tool: 0.940 with the guard, 0.936 without; these do not
  compare with the spec's 0.913, measured on another count of note words.
- **Gierke's endnotes** (b197fb9, 77d7ac8): 299 endnotes on pages 186 to
  282, 213 linked; the library card stays out (page 288 excluded, and no
  paragraph runs into or out of the section). Endnotes 2 to 6 now link
  to Gierke's own references. **Endnote 1 is still wrong**: "(1." on
  page 74, in the List of Authorities (pages 68–85, after the last
  contents page), takes it, and "Law1" on page 88 stays unlinked. One
  wrong pop-up and one missing; left as a known case.
- **Mariéjol's letter references** (S2): scored against the reference
  text, dropping them before matching gives 543 right references,
  matching first gives 521. The code's order is kept and the spec says
  so.
- **Tests**: a literal test for each of the 16 listed rules (each broken
  in turn, a test failing every time); four boundary tests in layout,
  plates and markdown; a whole-book test pinning Gierke's section.
- **Other**: one `model.note_places` used by structure and markdown;
  `_assemble.py` split in three; "A", "I", "a" before a known word are
  never markers; a hyphen joins across a line holding only a reference
  sign (Haskins page 71); a missing figure image is an input error
  naming its block; `body_measures.measured_page_positions` used by
  layout.
- **Not fixed**: Gierke's publisher lines (page 7) and printer's line
  (page 282) are small type below larger type, so they come out as
  footnotes; no spec rule covers them. The rule that would fix them (an
  unmarked band block in a book with no marker form is a paragraph)
  would turn 5 of Gierke's 7 real footnotes into paragraphs, so it is
  not taken.

After both merges, at the plan's branch: pytest 1418 passed in 27.6 s;
with 8 threads in 48.6 s; ruff, ty pass.

## Task 4.0 (5569c03 spec, fb90ec9; merged)

`domesday_headings_quotes` is re-cut to 11 pages: book pages 14, 22, 30,
39, 40, 42, 47, 93, 272, 274, 406. It now measures as the whole book
does: body height 10.0 (book 10.0, old excerpt 9.0), pitch 12.09
(12.135), marker form digits (None before); page 93 has 8 band blocks
and 10 notes, page 274 6 and 7, as on the whole book. The first index
page (546) is left out: its 50 rows of 8 pt type pulled the pitch to
11.5; its case, index page numbers overhanging the right column, is
left to the whole-book check (structure §9 says so). Page 47, a table
read as verse, is added.

## Task 7.6: re-reading Gierke's margin notes with Tesseract (a measurement for the owner)

Nothing was built; the script and full notes are outside the repository
(the session's scratchpad, `gierke-ocr/NOTES.md`). Method: galley's
layout on the whole Gierke; each page's margin strip cropped from a
300-dpi render (pypdfium2, one thread) and cut into notes at ink gaps
over 18 px (160 candidates on pages 86–185); Tesseract 5 `eng`, page
segmentation mode 6. Thirty notes chosen evenly, read by eye against the
crop, case and punctuation ignored:

| reading | words right of 139 |
|---|---|
| the scan's text layer | 52 (37%) |
| Tesseract, psm 6 | 133 (96%) |
| Tesseract, psm 6, image enlarged 2× | 134 (96%) |

On page index 88, the owner's example: the text layer has "Diverse",
"Unity of ment.", "Medieval Antique- Thought," and nothing for the
fourth note; Tesseract has "Diverse methods.", "Unity of the move.
ment,", "Medieval and Antique- Modern Thought." and "Medieval Thought."

Time, on a Mac17,9 (18 cores: 6 performance, 12 efficiency): the render
0.16 s a page, always in one thread; Tesseract 0.05 s a note (0.08 s a
page) on one thread, 0.95 s for the 100 pages on 12 threads. The render
sets the pace: about 50 s for the whole 290-page book.

What it would need: 23% of the candidates were pencil or ink marks, not
notes, which Tesseract reads as junk ("id i ;"), and junk gets into real
notes beside a mark; a filter is needed. One crop cut off a word; 10 of
layout's 157 margin regions fell outside every cut note.

## Task 3.2: margin notes before their paragraph (a146d35 spec, 5a49c61; merged)

Each margin note goes just before the paragraph beside whose line it was
printed, even when that paragraph began on an earlier page; the regions
of one printed note are one block; an indented line beside a note starts
a paragraph. structure §13 was clarified first (a146d35): rule 3 never
fires after a line ending in a hyphen (12 of Gierke's 13 such lines
continue a word), and applies only when the note lies outside the column
(Stubbs' cut-in notes indent their lines by about 60 pt; without this,
171 paragraphs would be split wrongly).

Whole Domesday, 611 margin notes from 640 regions: 604 placed before a
paragraph (547 beside its first line), 24 paragraphs split where a note
stands beside an indented line, 19 placed on the previous page, 7 inside
a footnote. Against the Gutenberg text the stream reported 240 of 263
matched notes before the same paragraph, but did not record how notes
were matched, and the review could not reproduce it; the reviewer's own
matching gives 61 of 64 on exact text and 185 of 213 at 0.8 similarity,
about 9 in 10 either way. The tool's margin-note scores come in 7.5.
The owner's example, Domesday page 30, now comes out right: "Serf and"
and "The serf of the Leges." each stand before their paragraph.

15 tests (`-k "margin_note_before or margin_note_inside or beside"`),
each rule broken in turn and a test failing. Nine reference pages
changed (Domesday 74, 75, 76, 83; Gierke 88, 270; Stubbs 51, 64, 59–60),
each named in the commit; the joined notes checked against the page
images ("The scale" + "holding.", "Natural" + "the level…", "Coercive"
+ "Force of"). On Stubbs page 51, "accession." goes before a paragraph
that still holds the chapter summary, until work package 4 makes the
summary a block. Task 3.2 is reviewed with work package 4.

## Task 7.4: the evaluation tool's new kinds (9a93672, 5ca7490, 4e325b8 spec; fb20ff7; merged at 1fe2519)

The change to `docs/specs/evaluation.md` went to the spec-reviewer before
the tool. It found one rule that would have scored galley better than it
is: a `verse` block on a prose quote counted right. Decided by the
orchestrator: the reader keeps poetry apart from prose quotes; `verse` is
right only on poetry, `quote` only on prose quotes, `chapter_summary`
only on the quote right after a chapter's label and title in Stubbs'
reference text (11 summaries). Also: at words and lines, endnote tokens
are not scored (galley's endnote words stay `extra` there); an endnote
linked more than a page from its reference is recorded with the cause
`endnote_reference_far`; `body_pages` is required (Haskins 16–279,
Stubbs 18–321, Domesday 22–552, before its imprint, Mariéjol 18–448),
and the heading scores are taken on it. The reference headings on those
ranges: 18, 26, 23, 26, as the plan's targets assume. Deliverable 4: 8
tests collected (4 asked).

## Work package 4: headings, chapter summaries, quotes and verse (20d0fc8, 89ee392, 59eee02; spec dd8a4dc, bfe483b)

Headings are centred lines, of level 1 or 2, with the chapter label in
`label`, none on contents pages; note references are also looked for in
headings (Kadesh's "STRATEGY*" stays linked). Chapter summaries and
verse are found per page; verse keeps a line feed at each printed line
end. Quotes by structure §16's rules 1–3, with the marker-led exclusion;
Haskins' bibliographical notes stay paragraphs. Spec corrections: the
Mariéjol verse reference pages (no verse runs over 51–52), and a
contents page makes no summary, verse or quote (Domesday page 14 had
given 5 false quotes).

Whole books (the stage's own counts; the tool's scores come in 7.5):

| book | reference headings in heading blocks, body range | quote blocks | verse blocks |
|---|---|---|---|
| Haskins | 18 of 18 | 29 | 2 |
| Stubbs | 25 of 26 | 66 | 0 |
| Domesday | 22 of 23 (and 4 false on the body range: table titles on pages 28, 42, 156, 470; the imprint on page 553 is a fifth, outside it) | 61 | 17 |
| Mariéjol | 26 of 26 | 11 | 13 |
| Kadesh | – | 23 | 0 |
| Gierke | – | 22 | 2 |

Stubbs has 10 chapter summaries, on the ten pages structure §15 names.
Known faults: Domesday's verse blocks are mostly tables; Stubbs' 66
quotes are its publisher's lists (the reference text makes them quotes
too); Gierke's 22 quotes are footnotes of Maitland's introduction left
in the body, since the book has no marker form; Haskins' index rows on
pages 267 and 271 are quotes until work package 5.

The excerpt `haskins_quotes_index` lacks the chapter II heading (book
page 41), so its bibliographical note runs on and its quotes on pages
53 and 71–73 stay paragraphs; these are checked by a whole-book test,
and page 41 is added to the excerpt in the review's fixes (decided by
the orchestrator).

Checks at 59eee02: pytest 1581 passed in 27.8 s; with 8 threads in 49.9
s; `-m whole_book` 30 passed in 242 s. Four reference pages changed
(Haskins 131 and 266, Kadesh 8, Stubbs 51).

## Review of task 3.2, work package 4 and task 7.4 (24d7d0f..977b2ed)

Four reviewers. The evaluation run at 977b2ed meets every heading, note
and margin-note target of structure §9: headings on the body range 18
of 18, 25 of 26, 22 of 23, 26 of 26; notes with the right reference
Haskins 59, Domesday 1,262 (target 1,250), Mariéjol 457; margin notes
Stubbs 241, Domesday 501. The fidelity reviewer found no word lost,
doubled or reordered in the six books, comparing the text order of
every block against the commit before. What mattered, all taken:

- **Margin notes of several pieces invented words**: a hyphen was
  joined across the gap between two pieces of one note, where a line
  went unread: 11 joins on Domesday and Gierke, 10 wrong ("peathe",
  "Persona", "Guardianvacant"), three recorded as certain. Decided: no
  join across the pieces of a note.
- **A real footnote became a bibliography paragraph** (Haskins page
  204, so "Adams,^" lost its pop-up). Decided: on the heading's page, a
  band block starting with the book's marker stays a note.
- **Verse started after a hyphenated line** (Mariéjol page 212, a false
  verse block of prose).
- **Notes lost between blocks and markdown in the scores**: Mariéjol's
  notes found as notes drop from 1,157 at blocks to 1,040 at markdown,
  Domesday's margin notes from 519 to 501, though the fidelity check
  passes. It predates this range; the cause is being found before 7.5.
- **Tests**: 15 of 76 mutants survived; five change real output or
  evaluation results (a 4-letter roman label "VIII" losing its label on
  Haskins page 233; the endnote-far cause; the summary rule). Each gets
  a test.
- **Conventions**: a list of notes built in two orders, so an index
  named different notes; `label` naming both an enum and a text; the
  tool copying two of markdown's rules with no test tying them.
- **Report corrections**: the 240 of 263 above, and Domesday's false
  headings on the body range are 4, not 5.

Fixes run in two worktrees: structure (`fix3-s`) and the evaluation
tool with the markdown investigation (`fix3-e`).

### The fixes (merged: fix3-e at 2dd81b2, fix3-s at c53962c)

- **Notes lost between blocks and markdown** were the evaluation tool's
  fault, not galley's: markdown writes a referenced footnote after the
  block that refers to it and an unreferenced one after its page's last
  block, so on a page with both the notes come out of printed order, and
  the tool paired notes page by page in order. The tool now takes the
  notes in `blocks.json`'s order at markdown. Mariéjol notes as notes at
  markdown 1,040 → 1,157 (as at blocks), missing 114 → 41; Domesday
  margin notes 501 → 519.
- **Hyphen joins across the pieces of a margin note**: 11 → 0
  (Domesday 6, Gierke 5).
- **Haskins page 204**: the footnote stays a note, linked from
  "Adams,^"; Haskins links 62 of its 64 footnotes.
- **Verse after a hyphenated line**: Mariéjol page 212's false verse is
  gone; the cost is page 243, whose two real verse lines follow "et
  pré-" and now run into the paragraph above (structure §16 records it).
- **The Haskins excerpt** has book page 41 added: its bibliographical
  note ends at chapter II and the footnotes on 53 and 71 are notes
  again. Its quotes on 53 and 71–73 still come out as paragraphs,
  because the excerpt is mostly small type (body height 7.6 pt against
  the book's 8.32); they stay checked by a whole-book test.
- **Looked at, not fixed** (no rule covers them): Domesday 443, "land."
  inside the body region's box; 456, no second line beside "The team-"
  in the text layer; Stubbs' reference margin notes that repeat a
  chapter summary's words, so the tool matches them to the summary.
- Tests for the guards no fixture reached; the conventions points; the
  six whole books' `blocks.json` unchanged by the refactoring.

The owner raised the default test run's budget to about a minute on 16
November 2026 (fb6b9c6). After both merges: pytest 1606 passed in 28.9
s; `-m whole_book` 30 passed (on the fix branch).

Work package 4 is done.

## Task 6.3: plates in structure (6ed5478 spec, d6f176b; merged)

A page with a figure is a plate: its running head goes, each other line
is caption when it has 2 known words or half its words known, the rest
is removed as `plate_text`; the caption becomes a figure block with the
plate's image, placed after the paragraph that runs over the plate;
paragraphs, hyphens and footnotes continue across a plate (a footnote
over a plate has its own test). A caption reads top to bottom by rows,
not in layout's order, which had scrambled Domesday page 39's caption
(decided by the stream, accepted by the orchestrator: it is the printed
order). All six EPUBs show their plates and pass epubcheck.

| book | figures | with caption | lines removed as `plate_text` |
|---|---|---|---|
| Kadesh | 16 | 5 | 6 lines, 12 words |
| Domesday | 2 | 2 | 17 lines, 68 words |
| Stubbs | 4 | 0 | 0 |

## Work package 5: index entries (b02de71 spec, b7f033a, 0488618; merged at 2851f51; sub-entries 0fc9544, 29e4318, 3a1bd01)

structure finds the index pages, reads each page's two columns, cuts
regions that cross the gutter, removes Stubbs' guide words (10, one on
each of pages 312–321), and makes `index_entry` blocks across columns
and pages. Rule 3's entry side was corrected by the orchestrator: where
continuation lines outnumber entry lines, the commonest left side is the
indent, so when at least 2 left sides lie more than 5 pt left of it,
the commonest of those is the entry side.

**Sub-entries, decided by the owner on 16 November 2026**: each
sub-entry is an `index_entry` block of its own with its depth in
`Block.level` (1 entry, 2 sub-entry; architecture §8), written with a
`.depth-N` class and indented by the style sheet. The orchestrator's
first question described sub-entries as printed on their own indented
lines; in Haskins and Stubbs they are run on after a ";". Told so, the
owner kept the split: an entry is cut after each word ending in ";".

Index paragraph boundaries, precision / recall:

| book | target | result |
|---|---|---|
| Haskins | 0.90 / 0.90 | 0.991 / 0.965 |
| Stubbs | 0.85 / 0.85 | **0.828 / 0.788**, missed: its OCR glues or loses ";" |
| Domesday | 0.90 / 0.90 | 0.990 / 0.986 |

Open: on Stubbs page 312 two garbled regions cross the gutter on too
many lines and come out as notes; Gierke's footnote words "List of" on
page 83 are a margin region taken into the index column; a "See …"
cross-reference stays in its entry, where Haskins' reference text makes
it an item. After the merges: pytest 1648 passed in 28.0 s; with 8
threads 49.3 s; `-m whole_book` 32 passed.

## Review of work package 5 and task 6.3 (dc65034..ee9e649), and the fixes

Four reviewers; fourteen fix commits (spec 5a411fa, 112ba13, 1c80849;
code 1a48d00 to e67a65c). What mattered, all taken:

- **Index page numbers attached to the wrong entry**: a margin region
  of an index column (the page numbers printed beside it) was placed as
  one block, so Domesday 546's "519" moved from "Beer" to "Bede" and
  Stubbs 321's "Wallingford" and "Walter" came out in three pieces. Each
  line of a margin region is now placed at its own top.
- **Gierke page 84's folio glued into an index entry**; **a Stubbs index
  entry linked as a footnote reference** (index entries are no longer
  searched for references, as captions are not); **Domesday's index
  running heads** "Index. 522" and "527 Index." left among the entries
  (now removed as running heads and page numbers).
- **A real caption word removed as stray** (Kadesh 48's "LUXOR"):
  decided by the orchestrator, a caption line is judged per printed row,
  not per piece of a row (structure §18; reversible by reverting 112ba13
  and 78a2d38). Kadesh 48 now keeps "l.i v IK RELIEFS; THE". Removed as
  `plate_text` after the fix: Kadesh 4 lines (8 words), Domesday 18
  (69).
- **Plate labels "PLATE II", "PLATE III" could be taken for running
  heads** in a book that prints them atop each plate: lines that differ
  only in a numeral are no longer alike. A plate page with two figures
  is refused with an error naming the page.
- **Tests**: about twenty rules of §17 and §18 survived mutation; the
  worst, the fitted edge of a slanted index column (without it Stubbs
  makes 916 entries, not 910). Each now has a test that fails when
  broken; one rule was dead code and is gone.

Index scores after the fixes: Haskins 0.991 / 0.965, Stubbs 0.829 /
0.789 (target 0.85 / 0.85, missed), Domesday 0.993 / 0.986.

Reported, not fixed (the rules as written give them): Stubbs' "Ma^arthy-"
on page 7 joined over its plates to a stamp "s" on page 12; Stubbs
312's ";;;" mark kept as a paragraph; Kadesh's piece on page 33 read as
a footnote and joined into page 36 across plates 34–35.

Checks at the end: pytest 1673 passed in 28.9 s; with 8 threads 50.3 s;
`-m whole_book` 32 passed. Work packages 5 and 6 are done.

## Task 7.3: the owner's check of the reference pages (f8babcb spec, edc1386, 3e9fa3f)

The sheet (67 sections, 193 checks, published privately on 16 November
2026) went to the owner, who checked 17 sections: D-14, D-22, D-30,
D-39, D-40, D-42, D-47, D-74, D-75, D-76, G-88, G-270, H-41, H-209,
H-266, K-8, M-51. The answers are exact tests (85 reference tests
collected, 66 asked). The other 50 sections are not checked by the
owner and have no new expected file.

What the owner found:
- **Kadesh page 16 is not a plate** but the scan of a cover, with no
  picture and no text: excluded in the configs (Kadesh now 15 plates,
  21 in all). Other faint Kadesh plates may be the same case; the owner
  will see them in the EPUB.
- Margin-note texts differ from the print where the OCR misread them
  (D-22 "Domesday Book and its satellites.", D-74 "The scale of
  free-holding", D-75's three notes, G-88's missing "Medieval
  Thought."): recorded as known, for re-OCR.
- **D-14, the contents page**: the owner reads its own structure —
  "ESSAY I." a heading, "DOMESDAY BOOK." a lesser one, the "§" lines
  grouping sections, a paragraph after each. galley makes no headings on
  contents pages, by the owner's decision of 15 November 2026; how a
  contents page keeps its own structure is open for the owner.
- D-47's blocks are three tables; D-42's links from table rows are wrong
  (known); G-270's first text the owner reads as a normal paragraph
  (galley gives it as the end of endnote 290, page 269 being outside
  the excerpt); M-51's footnotes cannot be read at all.
- G-88: "Law1" is in the page's first paragraph, not its last, as the
  sheet's question wrongly said.

Checks: pytest 1692 passed in 28.4 s; with 8 threads 49.5 s; `-m
whole_book` 32 passed.
