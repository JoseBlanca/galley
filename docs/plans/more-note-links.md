# Plan: more note references found and linked

The owner chose on 23 November 2026, after the second-book plan, to
link the notes galley still leaves unlinked: first the endnotes of their
own two books, then the footnotes of the public-domain books. The
breakdown below was approved in chat that day. Dated 23 November 2026.
State: under way.

Specs: `docs/specs/structure.md` (notes, endnotes, note references,
§34–§36), `docs/specs/correct.md` §9b (note links from the vision
model), `docs/specs/evaluation.md` (note scores). A rule this plan adds
goes into the spec in a commit of its own before the code.

## What was found (23 November 2026)

Two read-only investigations, on the EPUBs of `runs/small-fixes/`:

- **Turney (`turney`) and Haynes (`haynes`)**, the owner's books,
  copyrighted: 83 of 613 and 50 of 632 endnotes have no reference
  linked to them; none of the 1,112 existing links is wrong. Causes:
  the reference glued after a number or bracket ("1911.34", 18 + 31);
  a reference that is a word of its own (4 + 9); a superscript the OCR
  misread keeping some digits ("'9" for 19, 39 + 1) or none (quotes,
  `^`, `~`, letters, 22 + 1); a number followed by a dash and a word
  (0 + 4); a number after a word taken for a citation abbreviation
  ("art.27", 0 + 3); the note's own number misread (0 + 1). Besides,
  about 59 Haynes and 8 Turney endnotes are not notes at all: their
  number sits inside the previous note's paragraph.
- **Domesday (`domesdaybook00maituoft`)**: of 422 notes the evaluation
  scores as not right, 126 have galley's link on the right word; the
  evaluation maps a reference at a block's end past a following margin
  note, table, quote or "..." (`note_scores` in
  `tools/galley-eval/src/galley_eval/scores.py`). The real causes:
  notes joined because the next note's marker is misread (66); values
  shifted by a wrong count of notes earlier on the page (94, of which 68
  have a marker that reads true); note text in the body (14); a
  reference read as a letter or sign, `V`, `\` (28); glued to a number,
  "£16,000²" (22); split off as a word (25); a digit misread, 8 for 5
  (19); missing in the OCR (23); matching took another candidate (5).
- **Kadesh (`battleofkadeshst00breauoft`)**, with the vision model, 87
  of 179 notes unlinked: whole pages refused by the order check
  (`numbers_in_order` in `correct/_links.py`, 30 notes, 13 of them on
  pages where galley split or joined notes); notes of two columns
  joined (13); a garbled first word defeating `note_of` (43).

The investigations' per-note files, while the scratchpad lasts:
`/private/tmp/claude-501/-Users-jose-devel-book-parser/1ee0a54b-9041-40e0-8eea-a6a998ac4e20/scratchpad/footnotes/`
(Domesday per-note results and causes, Kadesh true notes per page) and
`.../scratchpad/endnotes/` (scripts only for the owner's books). The
counts above are what the plan's checks start from.

## In and out

In: the evaluation's count; the endnote references and the endnotes
run into each other; Domesday's footnote joins, values and references;
Kadesh's page refusals, column joins and garbled first words.

Out: reading Turney's superscripts again with Tesseract (gain not
measured); the 23 Domesday references missing from the OCR (only the
vision model can give them); tables.

## Rules that hold throughout

- No wrong link is the first condition: every new rule is checked for
  links it would make wrong, on the whole books, and a rule that makes
  one is narrowed until it makes none, or dropped.
- Nothing from Turney or Haynes enters a committed file: their tests are
  `whole_book` tests that count only; the unit tests use made-up
  sentences.
- `src/galley/note_references.py` is changed by work packages 2 and 4;
  they run one after the other.

## Before the first task

`samples/` holds the two PDFs of the owner; `samples/public_domain/`
the whole Domesday and Kadesh; `runs/small-fixes/` their last outputs.
LM Studio is needed only for 5.3, with the 35B model loaded by the
orchestrator and the owner's 27B model never touched.

## 1. The evaluation's note count

Map a reference at the end of a block to the gap after the block's last
aligned token, so that a margin note, table, quote or "..." after it
does not move it. Stream "eval": changes only `tools/galley-eval/` and
`docs/specs/evaluation.md`.

Deliverables:
1. A unit test of galley-eval with a reference at a block's end followed
   by a margin note, failing before.
2. galley-eval on Domesday's EPUB of `runs/small-fixes/`: notes whose
   reference is right rise from 1,307 by about 107–126, the other books'
   counts do not fall.

- [ ] 1.1 The fix, its test and the remeasure.

## 2. Endnote references in the owner's books

What counts as a reference candidate when matching endnotes: a number
glued after a digit or a closing bracket and punctuation; a number
followed by a dash and a word; no citation-abbreviation exclusion; a
lone 1–3 digit word, and a misread superscript (some of N's digits, or
a sign the book never prints otherwise), only in the gap between
linked neighbours N−1 and N+1. Stream "endnotes", after which comes 3;
changes `note_references.py`, `structure/_references.py`,
`structure/_endnotes.py`, `docs/specs/structure.md`.

Deliverables:
1. Unit tests on made-up sentences, one per candidate kind, and one
   each for the cases that must stay unlinked ("7 September", a time
   "10.35").
2. A `whole_book` test on each owner's book: unlinked endnotes 83 →
   at most 25 in Turney, 50 → at most 10 in Haynes, and every link's
   number and chapter equal to its note's (as the investigation checked
   all 1,112).
3. The fixture excerpts' outputs unchanged except for new right links.

- [ ] 2.1 Glued, dash and abbreviation candidates (cause A, D, E).
- [ ] 2.2 The gap between linked neighbours (B, C1, C2, F).

## 3. Endnotes run into the note before

Start a new endnote at "N." inside a note's paragraph when N is the
next number the chapter's notes expect and the words before it end a
sentence. Same stream as 2, after it.

Deliverables:
1. Unit tests, made-up, including a number that is not next ("see 12.")
   and stays text.
2. The `whole_book` test of 2 extended: Haynes' endnotes 632 → about
   690, Turney's 613 → about 621, still no wrong link; references to
   the new notes linked.

- [ ] 3.1 The split, its tests and the count.

## 4. Domesday's footnotes

In `structure/_notes.py` and the reference candidates: start a note at
a marker-form line after a short line; take the marker's own number
when it reads one and fits the page's order instead of the place; accept
a trailing `V` or `\` as a sign, the last digit glued after a
well-formed amount or year, a lone 1–2 digit word equal to the next
note's value, and 8 for 5 among confused digits. After stream
"endnotes".

Deliverables:
1. Tests on the excerpts the investigation named (`domesday_notes`
   pages 24, 35, 89; `domesday_lists` 141; `domesday_headings_quotes`
   42; `domesday_run_on` 468, 469; `domesday_74-83` 83), each failing
   before.
2. galley-eval on the whole Domesday: notes whose reference is right at
   least 150 more than after 1; no other book's count falls.

- [ ] 4.1 Joined notes and values from markers.
- [ ] 4.2 The reference candidates.

## 5. Kadesh's footnotes

Start a note at a marker at the top of a column; when a note's first
words are garbled, fall back on page order to find it; in the correct
stage, drop only the links that break the order, not the page's.

Deliverables:
1. Tests on `kadesh_8-17`, `kadesh_29-38`, `kadesh_59-68` for the joins
   (pages 13, 29, 36, 62, 63), failing before.
2. The model's answers on the three excerpts recorded once as fixtures,
   and a test of the narrower order check on them without the model.
3. Kadesh rebuilt with the vision model: links at least 92 + 30, none
   wrong on `tests/fixtures/expected/kadesh_reference/` and on the
   images of the pages with new links.

- [ ] 5.1 Column-top markers and the page-order fallback.
- [ ] 5.2 The narrower order check, with recorded answers.
- [ ] 5.3 The rebuild and the check by eye (orchestrator, LM Studio).

## 6. The end

- [ ] 6.1 Review per `reviewing-code`; all checks; the EPUBs of the
  seven books rebuilt in `runs/more-note-links/`, through epubcheck;
  galley-eval; the report.
