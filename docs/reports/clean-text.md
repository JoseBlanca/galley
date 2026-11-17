# Work report: clean text

The work of the plan `docs/plans/clean-text.md`, written as it goes, for
the owner. Started on 17 November 2026 on branch `plan/clean-text`.

## Summary

**The plan is done**, on branch `plan/clean-text` (17 November 2026),
and waits for the owner's order to merge it into `main`. Every check
passes at 7533d23: 2,111 tests in 47.6 s, the 61 slow tests on whole
books, and epubcheck (the EPUB validator) finds 0 errors and 0
warnings in the EPUBs of the six public-domain books. The books are
scans of about 1900 from the Internet Archive: Haskins, *The Normans in
European History*; Stubbs, *The Early Plantagenets*; Maitland,
*Domesday Book and Beyond*; Gierke, *Political Theories of the Middle
Age*; Mariéjol, *Catherine de Médicis* (French, a poor scan); and
Breasted, *The Battle of Kadesh*.

**What a reader of the EPUBs now gets:**

- Words the scan's own text (the OCR text the scanner put in the PDF)
  cut or glued are mended: "s ome" is "some", "Thisbookrestspartlyupon"
  is "This book rests partly upon", and "liter¬ ature" is "literature".
- The pages before the preface (endpapers, title page, copyright) are
  dropped, each dropped word recorded in galley's files. Haskins opens
  at its preface.
- The running head of a two-page section is removed ("vlil PREFACE" on
  the second page of Haskins' preface).
- Margin notes and index pages, printed small, are read again by
  Tesseract (an OCR program run by galley) and its reading is kept
  where it scores better. The share of wrong words in margin notes,
  against the online editions of the books, fell from 0.54 to 0.24 on
  Stubbs and from 0.58 to 0.14 on Domesday.

The plan set 8 numeric targets for these scores (reocr spec §9); all
are met but one, missed by one word: Gierke's 30 sampled margin notes
have 129 of 139 words right, against 130. The scores are in "Task 6.3"
and "Review 3" below.

**What is still wrong**, for the next plan:

- In Stubbs, about half the lines of the notes set into the text
  column (rather than in the margin) stay in the body text.
- On index pages neither the scan's text nor Tesseract is clean:
  of the 32 places where the two differ on Stubbs' page 312, the scan's
  text is wrong at 20 and Tesseract at 13.
  Taking the right reading word by word would fix most of them.
- Two short printed Stubbs notes are lost ("Motives de-", "Edward I.").
- Two words can come out in the wrong order where the scan's OCR set one
  word's box inside its neighbour's: on Mariéjol pages 210 and 214
  ("l'envoyé à" for "à l'envoyé"). Such nested boxes occur 447 times on
  249 pages of the six books; how many come out wrong was not measured.
- The owner's own two books need headings, running heads whose page
  number is set apart, notes collected at the back, and epigraphs.

**Asked of the owner:**

1. The order to merge into `main`.
2. A look at three EPUBs in `runs/clean-text/epubs/` of the main
   checkout, named by their Internet Archive ids:
   - `normansineuropea00hask.epub` (Haskins): it should open at the
     preface, with no garbage before it;
   - `domesdaybook00maituoft.epub` (Domesday): the margin notes around
     page 76, which were garbled ("dOTQ^tht villein.") and now read
     "The unfreedom of the villein.";
   - `earlyplantagenet01stub.epub` (Stubbs): the index, whose entries
     were glued ("siege of,116") and mixed.
3. A decision on the space printed before "?", ";", ":" and "!", as in
   Domesday's "pursued ?" (Domesday has 1,379 such spaces, Stubbs
   1,045, Mariéjol about 1,030 where French wants them):
   - (a) leave it: no work; on the Kindle a line can start with "?";
   - (b) a space that never breaks a line: a few lines in the step that
     writes the Markdown;
   - (c) attach the sign in English books and keep (b) in French ones:
     a recorded change of text in structure, a rule in the check that
     no word is lost, and the book's language from its config.
   Recommended: (c) in the next plan, (b) until then.
4. Nothing to do for this, but to know: the file the structure step
   writes (blocks.json, the book's paragraphs, headings and notes) has
   a new format version, 3, so a run of a book from before the merge
   must run the structure step again.

Four open points of the specs stay as built, and need no answer before
the merge: whether the EPUB shows a subtitle (recommended: a
`subtitle` key in the book's config), whether footnotes are read again
(off unless a book asks), whether junk Tesseract reads beside a margin
note is kept (kept), and that galley replaces words of the scan's text
with Tesseract's (as built).

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

## Task 2.4: "¬" as a line-end hyphen (added)

Added on 17 November 2026 after the owner read their own two books
(Turney, Haynes), whose OCR marks every line-end hyphen with "¬" (U+00AC),
leaving 1,020 and 2,219 broken words such as "liter¬ ature". Done
(spec af3de86, code 2d8ba46): "¬" at a line's end is joined exactly like
"-"; a kept hyphen is written "-". On the two books, by hand and not
committed: "¬" in `book.md` 1,020 → 0 and 2,219 → 0; 10 sampled joins of
each right. The public-domain books and excerpts do not change. The
fidelity check, which accepted only "-" as a joining hyphen, was changed
with it.

## Task 5.2: re-reading in layout

Done (refactor 85fa7fe; 7133cbd; the read-twice fix: spec 4c3a8de, code
8b4baef). layout re-reads the four kinds of region of reocr §3 and writes
a `Reread` record for each; `trust` and `redo` re-read nothing; a
missing Tesseract stops the command before any work. The review's
left-overs are done: layout's shared steps live in `layout/_column.py`,
the column rule and the small-row test are one function each.

**Words read twice.** As first built, the rule of review 1 (replace a
layer word only under a kept Tesseract word, widened 1 pt) left a word
read twice in 108 of 435 kept Domesday margin notes and 98 of 428 of
Gierke's, and doubled whole lines on two excerpt pages: the text layer's
lines sit a few points off the ink. Decided by the orchestrator and now
in reocr §4 and architecture §13: a layer word is replaced when its
middle lies under a Tesseract word widened 2 pt up and down and 1 pt
across (measured: 95 in 100 Domesday pairs and 92 in 100 Gierke pairs
lie within 2 pt; 2 pt never reaches the next line; 2 pt across took in
words Tesseract never read), or when its letters and digits equal those
of the nearest unmatched Tesseract word within 16 pt up or down (some
Gierke lines sit 15 pt off). One function, `model.replaced_layer_words`,
used by layout and the fidelity check. After: 0 of 421 Domesday records
and 2 of 417 Gierke ones read a word twice ("reignty", 25 pt off, page
244; "147" in a list of pages, page 63). Left: a garbled layer copy
stays beside Tesseract's reading when its text differs ("fllght'",
Domesday page 76; "lltes'", page 22); counted in task 5.4.

Regions read and kept, and layout's time with 6 workers on the Mac17,9:

| book | read / kept | time | reocr §7 |
|---|---|---|---|
| Stubbs | 359 / 228 | 29.9 s | 365 / 262, 30.7 s |
| Domesday | 623 / 425 | 68.5 s | 630 / 443, 69.9 s |
| Gierke | 758 / 417 | 50.1 s | 762 / 490, 52.0 s |
| Haskins | 17 / 9 | 4.0 s | 17 / 8, 3.5 s |

(Times are of the first build; the fix did not change the work done.)
Stubbs' index page 312 now has its guide words removed, and the book
gives 935 index entries against 839 before re-reading (910 before work
package 2). The changed reference pages, with layer and Tesseract
readings: `docs/reports/clean-text-reread-pages.md`. The excerpts take
their book measures from their own ten pages, so `stubbs_summaries_index`
has no small-print page; Stubbs' index read whole is held by a
whole-book test (task 5.4). Default run: 2,006 tests in 40.7 s, of
which 13.8 s is the excerpt fixture's setup, Tesseract included.

## Tasks 5.3 and 5.4: the re-reading tests

Done (d4f8bf1, 7825926; the garbled-copy fix: spec f1f24bf, code
28ddb6a). Deliverable 2: 34 tests with "reread" in `test_layout.py`,
among them Gierke's book page 88 reading "Medieval Thought.", Stubbs'
cut-in crops with the body lines as in a run with `ocr = "trust"`, 1 and
6 workers byte for byte, and Haskins' "^" read "1" with
`reread_footnotes`. Deliverable 5: 8 whole-book tests (the fidelity
check with re-reading on the six books; Stubbs with 1 and 6 workers;
Stubbs' index pages 312 to 321 read whole). A session fixture now runs
each whole book once for the layout and structure tests.

Deliverable 6, layout with 6 workers on the Mac17,9 (M5 Pro):

| book | regions read / kept | time | reocr §7 |
|---|---|---|---|
| Stubbs | 359 / 228 | 31.9 s | 365 / 262, 30.7 s |
| Domesday | 623 / 425 | 71.0 s | 630 / 443, 69.9 s |
| Gierke | 758 / 417 | 51.7 s | 762 / 490, 52.0 s |
| Haskins | 17 / 8 | 4.0 s | 17 / 8, 3.5 s |

**Garbled copies.** The count asked of 5.4 found a layer word left in a
kept margin note beside Tesseract's reading of the same word in another
spelling ("fllght'" beside "flight", Domesday page 76) in 38 of 421 kept
Domesday records and 15 of 417 Gierke ones; 4 of 5 looked at on the
page images were copies, 1 a real number Tesseract missed ("131.",
Gierke page 79). Decided by the orchestrator: a third match, a layer
word of 3 letters or more replaced when its letters are alike (ratio
0.6 or more) to those of the nearest unmatched Tesseract word within
16 pt; a word of digits only still needs an exact match. All 53 copies
have a ratio of 0.6 or more; the only words above it that are not
copies are two numbers. After: no copy at 0.6 on Domesday, 2 numbers on
Gierke (one real). Left, as a known limit: 10 copies spelled too unlike
("sey'" beside "Chertsey."), Domesday 7 of 421 records (1.7%), Gierke 3
of 417 (0.7%). Lowering the threshold to 0.5 would delete 4 real words
at the column's edge ("for" beside "lord"); matching a word that begins
or ends another was proposed and not taken, since it would also delete a
short real word beside a longer one ("its" beside "itself"). The new
match replaces 58 words; 10 checked on the page images were all copies.

Found, for the review: on Gierke's page 79, a numbered list, Tesseract's
junk is kept in 6 bands ("130. Ff" scores 2 against "130." at 1,
because "Ff" is in the word list).

Default run: 2,022 tests in 46.7 s (73.7 s with 8 threads); whole-book
run 59 tests in 562 s.

## The evaluation's front matter, again

Done (spec fdabd89, code 19c49be), merged. A window of 4 or more
consecutive missing reference tokens that prints, in order, words
galley dropped as front matter is left unscored, wherever it lies. On
Stubbs the series list now counts as front matter (301 tokens unscored,
against 17), and the body error rate at blocks goes back from 0.059 to
0.055. The stream's own run (on code with the first version of
re-reading, so not a clean before and after; in
`runs/clean-text-eval2-preview/`) also gave a first view of re-reading:
Stubbs' margin notes as margin notes 246 → 284 of 467 and their error
rate 0.537 → 0.260; Domesday's 522 → 574 of 593 and 0.583 → 0.161;
Stubbs' index recall .874 → .963.

## Review 2: work packages 3 and 5, tasks 2.4 and 4.2, review 1's fixes

Four reviewers on f90df04..13140e7. Every finding and its verdict:
`tmp/review2-findings.md` of the plan's worktree. What mattered, and
is fixed:

- **One Tesseract word stood for two layer words of different lines**
  (spec and fidelity reviewers, independently): on Domesday's index page
  548, "Dominium, 224" lost "Domini" and gained a "3", and the fidelity
  check passed, since it used layout's own pairing. Now a Tesseract word
  with any layer word under it is taken, and stands for layer words of
  one printed line only (nearest first); the fidelity check has a test
  of its own, not using layout's pairing, that a Tesseract word stands
  for one printed line. Looking at the 1 Domesday and 1 Gierke pair left
  more than 4 pt apart downward on the page images: neither is a word of
  another line.
- **A glued layer word kept beside Tesseract's two words** ("battle of,
  of,96 96", Stubbs' index): such a word is now replaced; 5 on Stubbs →
  0.
- **Tesseract's junk kept as characters** ("|", "¥", "©" from pencil
  marks): a token with no letter or digit is dropped unless it is
  punctuation or a printed sign; in kept records Stubbs 7 → 0, Domesday
  4 → 0, Gierke 24 → 0. Each record counts the tokens it dropped, a new
  field `dropped_junk_count` of `Reread` (0 by default; `lines.json`
  stays at version 2, since the field only adds).
- **A later region could keep again a word an earlier one had read**:
  dropped now; no case on the three books.
- **Smaller**: the command asked for Tesseract under `ocr = "redo"`,
  in which layout reads nothing; a Tesseract failure named neither page
  nor PDF; front matter warned on 9 of the 11 excerpts though it dropped
  nothing; untested guards of the front-matter rule and of re-reading;
  the line-end hyphens defined three times, one copy without "¬" (now
  `hyphens.py`); rules written twice in layout; dead code; layout's
  `__init__.py`, 1,264 lines, split into `_page.py` and `_rereading.py`
  (325 left, output byte-identical); the whole-book fixture made safe
  from two threads and shared by the extract tests (whole-book run 657 →
  584 s on a loaded machine).

Not taken: counting words under 3 letters and digits as neither known
nor unknown, proposed for Gierke's page 79 ("130." read "130. Ff"): it
would stop keeping Stubbs' index page 317 and cost 4, 2.4 and 10 in 100
of the kept margin records of Stubbs, Domesday and Gierke, beyond the 2
in 100 set beforehand. Gierke's page 79 keeps that junk; noted as known.

After the fixes, regions read and kept: Stubbs 359 / 228, Domesday 623
/ 428, Gierke 758 / 418. Stubbs' index gives 934 entries. All checks
pass at ee4c824: 2,043 tests in 46.9 s (74.3 s with 8 threads), 59
whole-book tests in 463.6 s.

## Task 6.2: the owner's sheet

Published privately on 17 November 2026:
https://claude.ai/artifact/ByAgVyaKbUxDxgNvJsAH2y, built at 89ed733 (15
checks with the page images, most important first; source
`tmp/sheet3/` of the plan's worktree). One asks for a decision (S-LOST:
whether to keep a one-word Tesseract reading where the layer has no
word, as for Stubbs' notes "Henry's" and "Coronation."). The owner's
answers go here when they come (task 6.4).

## Task 6.3: the final measurement

At 89ed733: `uv run galley-eval run`, in `runs/clean-text-final/` of
the main checkout; the whole-book tests, 59 passed in 462.5 s; the six
EPUBs in `runs/clean-text/epubs/`, each with 0 errors and 0 warnings
from epubcheck 5.4.0 (built one after another: Haskins 14.6 s, Stubbs
47.0 s, Domesday 95.4 s, Mariéjol 26.3 s, Kadesh 4.3 s, Gierke 65.2 s).

Scores at blocks, against the baseline (start of the plan) and the run
before re-reading. The tool changed during the plan (margin notes
scored as a part of their own; dropped front matter unscored: 41, 301,
79 and 32 tokens on Haskins, Stubbs, Domesday, Mariéjol), so the
baseline's body rates of Stubbs and Domesday are not comparable.

| score | baseline | before re-reading | final | target (reocr §9) |
|---|---|---|---|---|
| Stubbs' index precision / recall | .829 / .789 | .995 / .874 | .984 / .963 | ≥ .97 / .94, met |
| Stubbs' margin notes as margin notes, of 467 | 241 | 246 | 284 | ≥ 285, **missed by 1** |
| Domesday's margin notes as margin notes, of 593 | 519 | 522 | 571 | ≥ 560, met |
| Stubbs' body error rate | (0.142) | 0.059 | 0.055 | ≤ 0.062, met |
| Domesday's body error rate | (0.100) | 0.075 | 0.075 | ≤ 0.080, met |
| Domesday's notes whose reference is right | 1,277 | 1,278 | 1,278 | ≥ 1,275, met |
| Haskins' index error rate | 0.270 | 0.180 | 0.119 | ≤ 0.13, met |
| margin notes' error rate, Stubbs / Domesday | – | 0.537 / 0.583 | 0.259 / 0.161 | |
| Stubbs' margin notes in the body / missing | 189 / 37 | 193 / 28 | 172 / 11 | |
| Domesday's margin notes in the body / missing | 34 / 40 | 30 / 41 | 9 / 13 | |
| Domesday's paragraphs, precision / recall | .860 / .866 | .872 / .873 | .861 / .890 | |

Haskins' body error rate is 0.023 (0.024 before); Mariéjol changes only
on its bibliography, pages 14 to 16, as targeted. No kept Stubbs cut-in
record replaces a word of the column.

**Stubbs' margin notes, missed by 1.** Most wrong margin-note words of
Stubbs are lines of cut-in notes that layout leaves in the column
(page 70 "His" read "s"; page 93 "king" read "alking"), which
re-reading by rule never replaces; and crops read but not kept because
Tesseract misread a date (page 141, "1191" as "IIgi.", 1 against 2).
Stubbs keeps 228 of 359 crops, against 262 of 365 in the spec's
research run, the price of the rules that keep body words out of the
notes (review 2). What fixing it would take: finding more of the
cut-in notes' lines in layout (layout §9's rule finds about half), a
task of its own.

**Gierke's 30 margin notes, by eye** against 300-dpi renders: 129 of
139 words right (the text layer 52; target 130, **missed by 1**). The
words lost: page 139 "Theory of Cusanus." keeps only "Theory"
(Tesseract read it, but scored 1 against the layer's 2, since
"Cusanus." is not in the word list); page 123 loses "State.", which the
layer boxed 133 pt wide into the body column; pages 101, 112, 120, 148,
159 lose one word or a few to misreadings ("Ditferentiation",
"Repsesentation"). Counted right but flawed: page 125's words are out
of order ("Reversion 4 J of to power the People."), and some notes
carry junk or a repeated piece ("lty*", page 95; "Sovereisn-" twice,
page 128), from the layer where Tesseract's reading was not kept.

## Task 6.4: the owner's answers, and checking by eye

The owner answered 6 of the 15 checks (S-LOST, G-88, D-75, D-77, S-CUT
with the printed text of 25 margin notes; S-312 and T-74 in a line),
and asked that the assistant do such checks itself from now on. The
other checks were done by a subagent reading 300 to 800 dpi renders of
the scans; its answers and three whole-page transcriptions are in the
session's scratch folder, and the transcriptions are now in
`tests/fixtures/expected/index_*.txt`.

What the checks found and what was done:

- **The owner's 25 notes** are exact literals at blocks.json
  (`tests/test_layout.py -k "reread and owner_checked"`). 8 are strict
  xfails, each with its reason: Stubbs 51a and 64a (cut-in note lines
  left in the body), 60b, 61a and Gierke 88b (a final stop read as a
  comma), 62b ("advisers." lies under a body word), Domesday 75b on the
  excerpt (the join needs the whole book; a whole-book test holds it),
  and Domesday 75c ("pursued ?", an open question below).
- **S-LOST, decided by the owner's answer**: where the layer has no
  word, one known word of 4 letters or more, read at confidence 80 or
  more and standing alone, is kept. On Stubbs, Domesday and Gierke it
  keeps 24 regions, all printed (23 Stubbs note words and Domesday's
  "Kent."); Gierke's pencil "af" is at 69.
- **Words broken at a line end in margin notes**, where Tesseract lost
  the hyphen or read it as "." ("nation al", "move. ment", "posi.
  tion"): joined when the second part is rare after a line's first
  word in the book (at most 8 times). 32 joins on the three books, all
  right. In paragraphs the same rule made 11 wrong joins of 24 ("de
  facto"), so it is for margin notes only. A new word-change reason,
  `hyphen_lost`; **blocks.json goes to version 3**, so structure must
  be run again on older runs.
- **"_and"**: an underscore at a Tesseract word's end is stripped.
- **A tie lost printed words** (Haskins index page 267, "10 f." and
  "164 ff."): a tie now keeps Tesseract's reading when it has more
  known words. 34 of 423 ties on four whole books change. Page 267's
  differences from the transcription fell from 89 missing and 59 not
  printed to 22 and 22 (18 are ranges printed with an en dash).
- **Index pages S-312 and H-266**: neither reading is clean. On Stubbs
  312 the layer is right at 12 of the 32 places where they differ and
  Tesseract at 19; on Haskins 266, 3 and 24. Each page's differences
  from its transcription are now a frozen list a test compares. Taking
  the right reading word by word is for the next plan.
- **The 139 text-layer changes of work package 2**: 86 checked against
  the scans; all 58 joins and splits checked are right, 6 of 28
  regroupings wrong. The two that look like reordered words (Mariéjol
  210 "l'envoyé à", 214 "(i) »") were wrong before the plan too: the
  OCR set one word's box inside its neighbour's and layout sorts the
  row by position. A rule to keep the PDF's order there would touch 447
  word pairs on 249 pages, many where neither order is right, so none
  was made. Domesday 42 mixes two table rows. Left for later.

## Review 3: task 6.4's changes

Of cd75fcf..0f85025, by four categories. What mattered, all fixed
(0f85025..7533d23):

- **A printed word lost** (fidelity): the rule that replaces a layer
  word glued and misread over 2 or 3 Tesseract words replaced
  Domesday 547's correct "Devonshire," with "a aa". The layer word must
  now be unknown, and the rule runs after the other pairings, on
  Tesseract words of the same printed line. It replaces 5 words on the
  four books, all glued misreadings ("164Jf.;", "Sokeintiie").
- **A reading over no layer word kept at a score of 0**, against the
  spec. Kept when it holds 2 known words (Domesday 53 "Preedial element
  in serfage.", 439 "The caruea a constant.", both printed); the spec
  now says so. A single sure word must stand alone: this drops
  Stubbs 234 "Motives de-" and 258 "Edward I.", both printed, a known
  loss for the next plan (Roman numerals counted as known words would
  bring back the second).
- Four rules with no test that failed when broken; a `None` that
  switched joining on and off; a rule written twice; stale docs.

Scores after the review, against task 6.3's:

| score | 6.3 | now |
|---|---|---|
| Stubbs' margin notes as margin notes, of 467 | 284 | 291 (target ≥ 285, met) |
| Domesday's margin notes as margin notes, of 593 | 571 | 579 |
| margin notes' error rate, Stubbs / Domesday | 0.259 / 0.161 | 0.244 / 0.138 |
| Haskins' index error rate | 0.119 | 0.094 |
| Domesday's index precision / recall | .995 / .998 | .995 / .998 |

Every other score is unchanged. Checks at 7533d23: pytest 2,111 passed
and 8 xfailed in 47.6 s (75.5 s with 8 threads); whole_book 61 passed
in 464.4 s; ruff, ty and `uv lock --check` clean.

## For whoever next revises a skill or writes a plan

- A check sheet for the owner cost them time and gave less than a
  subagent reading the scans at 300 dpi or more. Expected text is now
  transcribed from the image by the assistant and recorded as such;
  the owner is asked for decisions only. A sheet that shows only the
  differences between two readings is hard to check: show the whole
  text beside the image.
- The excerpt tests did not catch a crash that only the whole of
  Domesday raised (a word broken at a line end in a tied reading). A
  rule change in re-reading should run `-m whole_book` before review.
- A reviewer's spec numbers that do not reproduce usually mean they
  were measured before the last rule went in: measure after the last
  code commit of a task.
