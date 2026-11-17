# Work report: clean text

The work of the plan `docs/plans/clean-text.md`, written as it goes, for
the owner. Started on 17 November 2026 on branch `plan/clean-text`.

## Before the first task

- **Specs.** `docs/specs/extract.md` and `docs/specs/front-matter.md`
  and the two-page running head of `docs/specs/structure.md` §3 were
  read by the first-reader and the spec-reviewer once; the reviewer's six
  findings were taken (straight quotes split off "told.", a split between
  two marks, excerpt checks that could not fail, the front matter's
  silent dependence on `contents_pages`, the evaluation tool hiding a
  lost preface start, two smaller ones). One answer of the writer was
  accepted against the reviewer: "introduction" is not a preface name,
  because without `contents_pages` it would end Stubbs' front matter at
  its page 20 and drop 1,182 words. `docs/specs/reocr.md` went through
  the spec-reviewer twice. The second review found that re-reading
  Stubbs' cut-in notes still replaced body words with Tesseract's junk
  (at least 34, "change" read "NE" on page 49) and took the page number
  on 8 pages; the spec now replaces no word of a body row, at a cost of
  margin notes found on Stubbs (326 → 293 of 467 in the writer's
  simulation).
- **One change to a spec by the orchestrator** (9e65986): a changed
  reference page is accepted when a script shows each change is a join,
  a split or a regrouping, and listed for the owner's sheet, instead of
  the owner checking each page before the commit.
- **The baseline**: `uv run galley-eval run` at b24b3e2 (code equal to
  `main` at 4542207), 2 min 1 s on the Mac17,9, copied to
  `runs/clean-text-baseline/` of the main checkout. It equals the final
  scores of `docs/reports/structure-second.md` on every figure the
  report gives there (notes whose reference is right 59, 1,277, 543;
  margin notes 241 and 519; index .829/.789, .991/.965, .993/.986;
  headings 18, 25, 23, 26).
- **Open points** of the specs, put to the owner in chat on 17
  November 2026, unanswered so far; the plan builds their meanwhiles.

## Work package 1: foundations

Done as planned. Task 1.1 (79cb64b): `pages.json`, `words.json` and
`lines.json` at version 2, the page kind and removal reason
`front_matter`, the `Reread` record (layout writes none yet), the
config keys `front_matter_end` and `reread_footnotes`, and the fidelity
check at layout that swaps a kept record's words. It also added
extract's case for a `front_matter` page (each word a removal), which
the type checker required once the page kind existed; analyze makes no
such page until work package 3. Task 1.2 (36e0e79): the excerpts
`haskins_front` (11 pages, 314 KB), `domesday_front_flow` (10, 487 KB)
and `gierke_front_flow` (10, 919 KB); every page has a text layer.

Checked by the orchestrator at the merge: deliverable 1's command passes
and lists 13 tests; deliverable 2, 8; deliverable 3, 6; deliverable 4
prints nothing; the evaluation tool's 346 tests pass; the default run
1,731 passed in 30.6 s, with 8 threads 53.7 s; `-m whole_book` 32
passed (task 1.1's run, 254.8 s). The excerpt fixture's setup went from
about 4.5 s to 6.0 s.

Review: this package is reviewed together with work package 2, which
first reads what it defines.

## Task 6.1: the evaluation tool (stream `eval`)

Done (8bbfe10), merged. The tool counts the dropped front pages and the
reference words before galley's first word as `front_matter_not_scored`
(the spec now says it counts both; 0 on every book until work package
3); scores the margin notes as a part of their own; and gives
`ocr_confidence_mean` over the words galley outputs, kept re-readings
included. Deliverable 1: 10 tests collected.

What changes the comparison with the baseline: with galley unchanged,
taking the margin notes out of the body moves 1,350 differences on
Stubbs and 1,510 on Domesday from the body to the new part. The body's
error rate at blocks falls from 0.142 to 0.129 on Stubbs and from
0.100 to 0.093 on Domesday, and the margin notes' own rate is 0.728
and 0.600. Later body rates are compared with these, not with the
baseline's. Haskins and Mariéjol are unchanged.

## Task 5.1: Tesseract and the pure parts of re-reading (stream `ocr`)

Done (aff3b50), merged. `ocr.py` runs Tesseract on a PNG and turns its
tsv into words in points; `layout/_reread.py` has the score, the
small-print page test, the note bands, each kind's crop and the words
each region replaces, and `page_rereads`, which keeps one record at most
per word. Deliverable 1: 62 tests, two of them marked `tesseract`.
Breaking 9 rules of `_reread.py` one at a time failed a test each time.

Differences from the spec, accepted: `read_image_lines` and
`lines_of_tsv` were added, because the first filter of the cut-in crops
drops whole Tesseract lines; no export from `galley.layout` yet, because
`_reread` imports layout's private steps and the export would be
circular (task 5.2 places it). Three choices the spec left open,
confirmed by the orchestrator: a note band replaces the margin words
whose middle lies in its crop (ink and 6 px); a Tesseract word inside an
earlier region's crop is dropped, kept or not, so no word comes twice; a
small-print page given other regions is an error.

## Task 4.1: the running head of a two-page section (stream `running-head`)

Done (31707ce), merged. structure takes a head line no other rule took
as a running head when one end word is number-like and the rest is like
the topmost line of one of the two pages before. Deliverable 1: 27
tests; each "kept" case fails when its condition is broken. On the
excerpts it fires only on the two target lines (excerpt page 6 of
`haskins_front` and of `domesday_front_flow`); on the whole books the
whole-book tests run structure on (Haskins, Stubbs, Gierke, Mariéjol),
only Haskins' "vlil PREFACE". Domesday and Kadesh are checked in task
4.2. A known limit, read literally from the spec: a speck above the
heading of the page two before would hide that heading.

## Work package 2: reading the text layer

Done (498b5c0, 636e1f4, 8b8ec5d), merged at f90df04. analyze and
extract read each page's words through `text_layer.layer_words`: the
characters in the PDF's order and glued words split at gaps. Checked by
the orchestrator after the merge: all checks pass, 1,849 tests in
30.7 s (53.9 s with 8 threads), 50 whole-book tests in 266 s. The
stream's deliverables: 13 unit tests, 6 excerpt tests, 12 whole-book
tests of the reading and 6 of the page kinds (unchanged on the six
books), and the word count of each book equal to extract §4's table
(Haskins 69,028; Stubbs 104,429; Domesday 251,053; Mariéjol 237,920;
Gierke 112,270; Kadesh 24,188).

**Changed reference pages.** 25 files of `tests/fixtures/expected/`
changed, with 139 changes of words: 81 joins ("s ome" → "some"), 33
splits (":—" → ": —") and 25 regroupings ("Ah igh" → "A high"), none of
another kind. Two block boundaries move with a word change on the page
next to them (Domesday 30/42, Haskins 209/210). The list, page by page,
is `docs/reports/clean-text-changed-pages.md`; it goes on the owner's
sheet (task 6.2).

**Scores** (`uv run galley-eval run` at f90df04, in
`runs/clean-text-wp2/` of the main checkout), against the baseline; the
body rates of Stubbs and Domesday are compared with those of task 6.1's
tool (0.129 and 0.093), since the margin notes left the body there:

| score, at blocks or markdown | Haskins | Stubbs | Domesday | Mariéjol |
|---|---|---|---|---|
| body error rate | 0.087 → 0.025 | 0.129 → 0.056 | 0.093 → 0.075 | 0.324 → 0.310 |
| notes error rate | 0.404 → 0.169 | – | 0.101 → 0.091 | 0.694 → 0.686 |
| margin notes error rate | – | 0.728 → 0.537 | 0.600 → 0.583 | – |
| notes whose reference is right | 59 → 61 | – | 1,277 → 1,279 | 543 → 567 |
| margin notes as margin notes | – | 241 → 245 | 519 → 522 | – |
| index precision / recall | .991/.965 → .997/.988 | .829/.789 → .995/.874 | .993/.986 → .999/.993 | – |
| paragraph precision / recall | .859/.898 → .866/.909 | .742/.737 → .743/.744 | .860/.866 → .869/.877 | .730/.752 → .732/.755 |

What got worse: Mariéjol's notes missing 41 → 47 and notes as notes
1,157 → 1,154; Domesday's unplaced words 3 → 4. Found by the stream and
decided by the orchestrator:

- Stubbs' index page 312: the letter soup is now words, but its 74
  entries come out as 34 notes and its guide words "BAL BEC" are no
  longer removed; the book's index entries fall from 910 to 839 (the
  scores above count paragraphs, which rose). The page is a small-print
  page that work package 5 reads whole; it is checked again after it.
- Kadesh page 8: the note "a In Ramses…" lost its marker "a": once "I n"
  is "In", "a" reads as the article. A defect of structure's marker
  rule; fixed with the review's findings.
- Gierke page 85: "No. 53" lands in the entry "Torquemada", because the
  scan's OCR laid it over that line (seen on the page image). Not
  galley's.

`split_glued` takes the larger of the two middle widths as the median;
with their mean, "A.d." on Stubbs' page 207 is split. extract §4 now
says so.

## Work package 3: the front matter

Done (e88abc3, 54467ba), merged. analyze finds where the front matter
ends and makes the text pages before it `front_matter`; extract records
each of their words as a removal. On the six whole books the ends,
steps, pages and word counts equal front matter §4:

| book | end | step | dropped pages | words |
|---|---|---|---|---|
| Haskins | 12 | preface | 1, 2, 6, 8, 9, 10 | 108 |
| Stubbs | 14 | contents | 1, 6, 7, 12, 13 | 370 |
| Domesday | 12 | preface | 4, 8–11 | 99 |
| Mariéjol | 10 | preface | 6–9 | 95 |
| Gierke | 10 | contents | 1, 6–9 | 100 |
| Kadesh | 8 | running text | 4–7 | 91 |

Deliverables: 37 unit tests, 16 excerpt tests and 12 whole-book tests,
all passing; no reference literal of an old excerpt changed. After the
merge the default run is 1,901 tests in 45.1 s, within the minute but
up from 30.7 s since the plan started; the whole-book run took 467 s.

Decided by the orchestrator: Kadesh, which has no contents, logs a
warning on every run that its front matter was found by the running
text alone; that is the warning's purpose, and `front_matter_end`
silences it. Front matter §6's first unit test gives Haskins' pages 0
to 27 alone, which make a window of 10 pages and an end of 0; the test
adds stand-in pages, and the spec is corrected with the review's fixes.

## Review 1: work packages 1 and 2, tasks 4.1, 5.1 and 6.1

Four reviewers (spec, tests, fidelity, conventions) on d8075e6..f90df04.
Every finding and its verdict: `tmp/review1-findings.md` of the plan's
worktree (not committed). What mattered, and is fixed:

- **A kept re-reading could drop printed words unseen** (fidelity).
  A region replaced all its layer words although some of Tesseract's
  words for them had been dropped; in the reviewer's simulations a
  cut-in note lost "wcnt nortb" and a footnote band lost "See Stubbs",
  and the fidelity check passed. Now a layer word is replaced only when
  a kept Tesseract word lies over its middle (widened by 1 pt), an
  earlier crop drops Tesseract's words only when its region was kept,
  and the fidelity check fails on a replaced word no Tesseract word
  covers (spec 378c443, code 5c63c89). A margin word wholly outside the
  strip now stays in the layer; the cost, a word that could be read
  twice where the layer and Tesseract place it differently, is measured
  in task 5.2.
- **A band with no layer words kept Tesseract's junk** (spec): "af"
  from a pencil mark on Gierke's page 120. Such a region is now kept
  only with at least 2 known words (spec 0c930ea, code d070bce).
- **A lost note marker** (found by the text-layer stream): a lower-case
  "a" before a capital is now always a note's marker. Two notes on the
  six books change, each a superscript the OCR misread, checked on the
  page image: Kadesh n-p0008-003 "In Ramses…" and Domesday n-p0439-003
  "See e.g." (spec 658625b, code 6e8e226). The Kadesh reference page
  has its marker again, as the owner checked it on 16 November.
- **Rules no test held**: the tie of the reading score, the cut-in
  crop never replacing a body word, seven more thresholds of
  re-reading; the marks of `split_glued` (a hyphen at a wide gap passed
  the default run); the number-like condition of the short-section
  rule; five rules of the evaluation tool. Each has a test now that
  fails on the reviewer's mutation.
- **Conventions**: the meaning of a kept re-reading coded twice (now
  `model.words_after_rereads`); `note_bands` took pixels without a DPI
  (now refuses any but 300); constants defined twice.

Not taken, with the reason: the short-section rule's speck condition
could never be met (the line on such a page is the speck, under 4
letters), so it was removed instead of tested, changing no output; the
verdict's "no more unknown than known words" for an empty-layer region
adds nothing to a score above 0. Left to task 5.2, which wires
re-reading into layout: the circular import of layout's private steps
into `_reread`, the column rule written twice, Tesseract not checked at
start-up, a public name for the side type. A known limit: Stubbs' page
218 "A.d" is cut into "A." and "d" (a closing mark, then a letter, at
1.97 pt against 1.35).

## Task 4.2: the short-section tests

Done (d1c8727). On `haskins_front` and `domesday_front_flow`, excerpt
page 6, the running head is removed (Domesday's "vi" recorded as a page
number); on the six whole books the rule adds exactly page 13 of
Haskins and of Domesday. The whole-book test runs in 72 to 78 s alone.

## The scores before re-reading

`uv run galley-eval run` at fbdc71f (work packages 1 to 4 and review 1
merged), in `runs/clean-text-before-reread/` of the main checkout, the
"before" of reocr §9's targets. Against the run after work package 2:
the front matter is dropped on the four books, and the tool leaves 32,
17, 6 and 25 reference tokens unscored as front matter (Haskins,
Stubbs, Domesday, Mariéjol). Haskins' paragraph precision rises from
.866 to .885; the other scores move by 0.003 or less, but for Stubbs:
its body error rate rises from 0.056 to 0.059 and its paragraph recall
falls from .744 to .733. The cause is the tool, not lost text: 344
reference tokens of Stubbs' series list ("Epochs of Modern History,
edited by…"), printed on the front pages galley now drops, count as
missing, because the tool leaves front matter unscored only before
galley's first aligned word and a title word aligned first. The tool
is changed after task 5.2 to leave unscored a run of reference tokens
that matches a run of dropped front-matter words.
