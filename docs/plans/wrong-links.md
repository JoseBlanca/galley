# Plan: fewer wrong note links, fewer notes joined

The owner chose on 24 November 2026, after counting the wrong links of
every book, to remove the wrong links galley's structure stage makes and
to cut apart notes read as one. The breakdown below was approved in chat
that day ("option 1"). Dated 24 November 2026. State: under way.

Specs: `docs/specs/structure.md` §11 (notes and their references, where
a note starts, the marker of a note, references), §12 (endnotes, for the
numbering rule it already has), `docs/specs/evaluation.md` (note
scores). A rule this plan adds goes into the spec in a commit of its own
before the code.

## What was found (24 November 2026)

Every link of the current builds (`runs/more-note-links/<folder>/`,
Kadesh `runs/kadesh-links/battleofkadeshst00breauoft-final/`) was
checked against galley-eval's transcriptions (Domesday, Haskins) or the
page images (all of Kadesh; samples of Gierke, Turney, Haynes). Wrong:

- **Domesday (`domesdaybook00maituoft`)**, 10 of 1,589, page indices:
  - a sign that is no reference (`*`, `^`, `•`) linked to a note while
    the page's real reference was misread: 106 (a closing quote read
    `*`, linked to the printer's signature "M." taken for a note), 154,
    498;
  - table rows taken for unmarked footnotes and numbered by
    `page_values` (`structure/_notes.py`): 200, 499 (2);
  - two notes on one line left joined, the next note then numbered one
    off: 440 (reference 5 opens note 6), 517;
  - a number starting a continuation line read as a new note's marker:
    445;
  - the reference digit misread by OCR: 333 ("2" read 3).
- **Haskins (`normansineuropea00hask`)**, 1 of 69: page 204, a sign.
- **Kadesh (`battleofkadeshst00breauoft`)**, 8 of 105 from the structure
  stage (and 2 from the vision model, both on page 21): pages 14 (two),
  15, 21, 27, 31, 55, 61. On 21 and 27 three printed notes are one
  record (48–50, 64–66); the others point to the note before.
- Gierke, Turney, Haynes: none in 102, 103 and 61 links checked by eye.

Notes whose link is right but whose text also holds the next note
(found by comparing texts, not checked by eye): Domesday 24, on pages
52, 57, 78, 111, 123, 135, 136, 145, 157, 167, 177, 187, 207, 213, 225,
235, 258, 269, 335, 376, 440, 449, 504, 517; Haskins 1, page 29.

The investigation's scripts were in a session's temporary folder; work
package 1 makes the measure part of galley-eval.

## In and out

In: the structure stage's footnote cuts and numbering, the scoring of a
sign against a note, and galley-eval's report of wrong links and joined
notes.

Out: a reference digit misread by the OCR (Domesday 333), which no rule
tells from a right reading without losing right links; the vision
model's two wrong links on Kadesh page 21 (they may go when the notes
are cut apart, and are not targeted); a link the model places one word
off (`docs/reports/more-note-links.md`); tables, which galley does not
yet make.

## Rules that hold throughout

- No new wrong link. Every link a work package adds or moves is checked
  on the page image or against the transcription.
- The other books' outputs stay byte-identical unless the change is
  meant for them; any difference is listed and checked.
- Examples in code, tests and commits come from public-domain books or
  are made up; nothing from Turney or Haynes.
- The tests' default run stays near a minute.

## Before the first task

- `samples/public_domain/` holds the four books (Domesday, Haskins,
  Kadesh, Gierke) and `runs/more-note-links/` the current builds.
- No LM Studio is needed until 5.2.

## 1. The measure

galley-eval reports, per book, the links that go to a note other than
the transcription's, and the notes whose text holds the next note's
start, each with its page index. Changes only `tools/galley-eval/` and
`docs/specs/evaluation.md`.

Deliverables:
1. Unit tests of both reports on made-up texts, failing before.
2. galley-eval on Domesday and Haskins at the starting commit gives the
   lists above: wrong links 10 (Domesday) and 1 (Haskins) once the
   evaluation's own misalignments are checked by eye, joined notes 24
   and 1. The command and its counts go into the report as the baseline.

- [x] 1.1 The two reports, their tests and the baseline.

## 2. Unmarked notes and signs

A footnote with no marker of its own is linked only when it is sure:
the note before it on the page is linked and the reference reads the
next number, or it is the page's only note. A sign (`*`, `^`, `•`) read
where a reference is expected pairs with a note only under the same
condition. Changes `structure/_notes.py`, `structure/_references.py`,
`docs/specs/structure.md`.

Deliverables:
1. Unit tests, made up: a table row under a page's last note; a sign
   paired with a note that is not next; the page's only unmarked note
   still linked.
2. Domesday whole book: the wrong links on 106, 200, 499 (2) gone, and
   154, 498, Haskins 204 gone or said why not; the 12 right links to
   unmarked notes (10 Domesday, 2 Haskins) kept; galley-eval's right
   count not lower than 1,563 (Domesday) and 68 (Haskins) less the
   links removed as wrong.

- [x] 2.1 The rule, its tests and the remeasure.

## 3. Notes joined on one line, and continuation lines

Cut a footnote where a second marker starts on the same line, after a
sentence's end, and is the next number; keep a marker's own number when
a reference on the page reads it, as the endnote matching does (§12),
instead of the per-page numbering's. A number that starts a line inside
a note is a marker only when it is the next number and the line before
ends a sentence. Changes `structure/_notes.py`, `structure/_markers.py`,
`docs/specs/structure.md`. After 2 (same files).

Deliverables:
1. Tests on the Domesday excerpts for the pages they hold, and a new
   excerpt (`scripts/fetch_samples.py`, about ten pages) for pages 440,
   445 and 517 and some of the joined ones, failing before.
2. Domesday whole book: the joined notes 36 (galley-eval's count,
   work package 1; the investigation had found 24) → at most 12; the wrong
   links on 440 and 445 gone, 517 linked right or unlinked; no new wrong
   link. Haskins page 29 cut.

- [ ] 3.1 The new excerpt and the cut on one line.
- [ ] 3.2 The marker's own number, continuation lines, remeasure.

## 4. Kadesh's wrong structure links

Pages 14, 15, 21, 27, 31, 55, 61: after 3, see which remain; for each,
the cause, and a rule that unlinks it (or links it right) without losing
a right link on the three Kadesh excerpts. A page no rule fixes is said
in the report with its cause. Changes the files of 3. After 3.

Deliverables:
1. Excerpt tests on the pages the Kadesh excerpts hold (14, 15, 31, 61)
   against `tests/fixtures/expected/kadesh_reference/`, failing before.
2. Kadesh rebuilt without the vision model: wrong structure links 8 → at
   most 2, right links not fewer than before (by the page images).

- [ ] 4.1 The causes and the rules.

## 5. The end

- [ ] 5.1 Review per `reviewing-code`; all checks; the EPUBs of the
  seven books rebuilt in `runs/wrong-links/`, through epubcheck;
  galley-eval; every changed link checked on the page images; the
  report.
- [ ] 5.2 Kadesh with the vision model, if the owner says LM Studio is
  free (about 26 minutes; the 35B loaded by the orchestrator, the
  owner's 27B never touched).
