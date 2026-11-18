# Report: stray text in the body

The work report of `docs/plans/stray-text.md`, written as the work goes,
for the owner. Started on 18 November 2026.

## Before the first task

The plan was written on 18 November 2026 from two investigations of the
eight books' runs at main a0a1675; the owner said to write it and go on
without waiting. Pandoc, Tesseract and epubcheck are installed; the
public-domain books and the owner's two PDFs are in `samples/`.

Two of the defects the owner reported on 17 November are already fixed
on main: the Haskins running head left in a paragraph (page 23) and the
Haskins footnote of page 28. The plan only checks them.

The investigations' notes and scripts are in `tmp/investigation/` of the
plan's worktree (not committed: they quote the owner's books).

## Work package 1: the specs, the formats and the excerpts

Done in three commits: be06218 (specs), 5141c9f (formats), b54be14
(excerpts). The checks pass: ruff, ty, and pytest with 2,810 passed and
24 expected failures in 80 s (8 threads: the same counts in 128 s).

- **Specs.** The inkless page is a new section 2b of `docs/specs/plates.md`,
  where the 36 dpi render is specified; architecture §8, §9 and §17,
  the glossary, layout steps 2b, 3, 4 and §9, and structure §3, §9 and
  §11 are amended. The first reader and the spec reviewer read them.
  Not taken: requests to define terms layout defines elsewhere, and a
  recount of Haskins 278 at 0.88 for 0.92, which leaves the margin as it
  is.
- **Formats.** pages.json is version 4, with the page kind `inkless`;
  removals gain the reason `inkless_page`. words.json is unchanged.
- **Excerpts.** `haskins_endpapers`, `domesday_notes`,
  `gierke_notes_heads`, `stubbs_cut_in`, with 26 expected files read
  from the page images, and 16 tests marked as expected failures until
  their work package lands.
- **Changed from the plan:** six thresholds and pages, listed in the plan
  under "Changed by work package 1". Each was measured on the eight
  books before it was changed.
- **For the owner:** the quick tests take 80 s, from 70 s; task 5.3 is
  to bring them back. Haskins 277 holds a printed conservator's label
  without text-layer words, so removing the page's words loses no print.

## Work package 2: inkless pages

Done in three commits, merged from the `analyze` stream: b84b80c
corrects the spec's share for Haskins 278 from 0.92 to 0.88 (21 of 24
words without ink; the margin below the lowest inkless page is 0.38);
30ff1c7 marks the page in analyze; 3a36c9a tests the eight books.
extract needed no change.

- `uv run pytest -m whole_book -k inkless`: 8 passed, the owner's books
  included. The inkless pages of the eight books are exactly Haskins 277
  and 278 and Haynes 9 and 421; Haskins' endpapers 1 and 2 stay front
  matter.
- After the merge: ruff and ty pass; pytest 2,826 passed, 22 expected
  failures, in 106 s while two other streams were running tests on the
  same machine.
- `tests/test_layout.py` changed in this stream, outside its files:
  `haskins_endpapers` is the one excerpt with no measures, since only
  its colophon is text now. Both tests still check the other excerpts.

## Task 3.2: the running-head survey and reference candidates

Merged from the `structure` stream: 2a16b54 (the survey compares heads
whose letters differ by up to 14), bbc5723 (a sign followed by
punctuation is a reference candidate), 022e957 and e5fd492 (a spec
amendment and its code: such a sign after one letter alone is not a
candidate, because Domesday prints "St." 28 times and its OCR reads
"S*.").

- Running heads: 3 more removed on the eight books, Gierke 16 and 84
  and Mariéjol 158; no heading and no other removal changed.
- Domesday references linked: 1,493 at a0a1675, 1,514 now. The 23 new
  links of the first rule were checked on the page images: 21 right and
  2 wrong ("S*." on pages 285 and 333), and the second rule removes
  exactly those 2. On page 77 two references now go to the right notes,
  one of which was wrong before. The other seven books gain no links.
- Domesday notes without a reference: 343 at a0a1675, 322 now; the
  whole-book test allows 328. The plan's measure of 178 unlinked
  references came from the evaluation; this count is structure's own.
- The one-letter rule applies only when punctuation follows the sign: a
  "T*" with nothing after it stays a candidate, because the broader rule
  would unlink a reference on Kadesh 39 that was not checked.
- After the merge: ruff and ty pass; pytest 2,838 passed, 19 expected
  failures, in 88 s with the layout stream running alongside.

## Review of work packages 1, 2 and task 3.2

Four reviewers (spec, tests, fidelity, conventions) read a0a1675..b3fa355.
None found a lost, duplicated, reordered or invented word; the fidelity
reviewer ran the eight books and found pages.json changed on exactly the
four inkless pages. All findings were taken and fixed in 10 commits
(01ed153 to e74cbf1):

- a page both the plate rule and the inkless rule take was logged as a
  plate; now only plates are;
- the inkless comparison was written twice, and the filter of excluded
  regions was untested; one function now decides, and a test on Haskins
  278 with an excluded region fails without the filter;
- a short page of faint real print could be removed whole (Gierke 1, a
  binder's label, has 2 of 7 words below the ink threshold). A page is
  now not inkless when at least half its words without ink are known
  words: Gierke 1 is at 0.50; the four inkless pages are at most 0.17
  (Haynes 9, "SP"). The inkless pages of the eight books are unchanged;
- the running-head limit of 14 had also reached two callers outside the
  survey (the top line of a plate, the head of a short section); they
  keep 8;
- stale numbers in comments, docstrings and the specs.

## Tasks 3.1, 3.3, 3.4, 4.1, 4.2: the layout half

Merged from the `layout` stream: c9aa1fd (a 2- or 3-digit page number
boxed above its head joins the head row), 522617f (footnote rows small
against their page; one-line notes start the band), db59076 (whole-book
tests), d075104 (Stubbs' cut-in rows with smaller strip words), 34ce6e0
(whole-book tests). After the merge: ruff and ty pass; pytest 2,883
passed, 10 expected failures, in 81 s.

Whole-book counts, a0a1675 against now:

| what | before | now |
|---|---|---|
| Kadesh 38, Domesday 200 and 428 heads removed as running heads | 0 of 3 | 3 of 3 |
| Stubbs' margin notes left in the body | 169 | 46 |
| Stubbs' margin notes found as margin notes | 291 | 413 |
| Stubbs' strip words the evaluation pairs with the body | 24 | 31 |
| Gierke introduction pages with their notes as footnotes | 0 of 27 | 0 of 27 |
| Domesday one-line notes and Gierke 61's as footnotes | 1 of 11 | 1 of 11 |

The head rule also changes Domesday 552, a head of the same kind. Of
the 7 new Stubbs words paired with the body, 2 are note words.

**Not yet done.** Layout now makes Gierke's introduction notes and
Domesday's one-line notes into footnote bands, but structure still
refuses them: its band-region test takes only words at most 0.85 of the
book's body height. Task 3.5 is added for it. A new cut-in zone on
Stubbs 56 lets Tesseract's re-reading add "[dy", the tops of body
letters, as a margin note; task 4.3 is added, and the test asserting the
clean reading is an expected failure until then. The plan's own counts
of one-line notes (8, then 10) and Stubbs pages 34 and 143 changed as
"Changed by work package 1" says.

The stream changed `tests/test_excerpts.py` and the expected files of
`stubbs_51_56-64` pages 0 and 9 outside its files, with leave: the rule
takes whole notes out of the body lines of Stubbs 51 and 64, and the
new expected text was compared with the page images at 200 dpi.

## Task 4.3: re-read words at a cut-in crop's edge

Merged: 2b0700e (`docs/specs/reocr.md` §3 and §8, where layout's spec
puts the cut-in crop's filters) and 5552d40. The crop on Stubbs 56 ended
at 150.5 pt, through the tops of the body line below; Tesseract read
them as "[dy" (confidence 5), which overlapped no body word's box. A
re-read word within 3 pt of a cut-in crop's top or bottom is now
dropped. On whole Stubbs, 5 words came within 1.6 pt of an edge, each
the top of a cut body line on the page image (pages 56, 102, 127, 177,
283); the nearest real word is 10.7 pt inside. Re-read words kept:
Stubbs 6,387 to 6,373 (the 5 junk words, and 9 words of two notes on
pages 102 and 177 that the text layer now gives with the same text);
Domesday 4,955, unchanged. pytest: 2,885 passed, 9 expected failures;
`pytest -m whole_book -k stubbs`: 8 passed.

## Task 3.5: footnote bands measured against the page in structure

Merged: 6e7cc3b and 4704e2c (structure §1, §2 and §16), ed5c47c (code
and tests), ea13ac0 (two whole-book tests corrected). structure now
accepts the bands layout finds: a footnote band is measured against
the page's own rows, and a one-line note is a band when it is the
page's last region, holds one line opening "1" and a capital, and lies
below the body. A second fix keeps Gierke's endnotes as before: its
marker form becomes digits, which had cut 79 of its 299 endnotes in
mid-sentence until the rule that caused it was left out of the endnote
section.

| book | footnotes before | after | notes without a reference before | after |
|---|---|---|---|---|
| Gierke | 2 | 69 | 93 | 98 |
| Domesday | 1,837 | 1,847 | 323 | 323 |
| Mariéjol | 1,114 | 1,120 | 424 | 426 |

The other five books do not change. Gierke gains footnotes on 32
pages: all 27 introduction pages, page 61, and 109, 146, 147 and 156.
Domesday's ten one-line notes are all linked. Seven changed pages were
checked against their images (Gierke 15, 37, 61, 109; Domesday 163, 185;
Mariéjol 245).

Two whole-book tests were wrong, not the code: the one-line test took
Gierke's contents page number "1 1 6" for a note left in the body, and
now looks for "1" followed by a capitalised word; Haskins' count of
footnote pages fell from 65 to 64 because page 277, an endpaper whose
pattern the text layer read as a footnote, is now inkless.
After the merge: ruff and ty pass; pytest 2,895 passed, 6 expected
failures, in 82 s.
