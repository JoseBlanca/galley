# Report: stray text in the body

The work report of `docs/plans/stray-text.md`, written as the work goes,
for the owner. Started on 18 November 2026.

## Summary

The plan is done on branch `plan/stray-text`, on 19 November 2026, and
waits for the owner's order to merge it into `main`. It removes four
kinds of stray text from the middle of a book's text, on the eight books
galley is tried on: the owner's two (Haynes, Turney) and six
public-domain scans (Haskins, Domesday, Stubbs, Gierke, Kadesh,
Mariéjol).

What a reader of the EPUB sees now:

- **Junk of blank pages is gone.** A page that prints nothing but whose
  scan still carries OCR text (a blank back of a leaf, a patterned
  endpaper) is recognised because at least half of its words have no
  ink under them on the page image; its words are left out, each with a
  record. This removes "SP I fiyj. £ v" after Haynes' contents and the
  junk of Haynes page 421 and Haskins' back endpapers. A page is kept
  when 2 or more of its inkless words are real words.
- **Running heads boxed apart from their page number** are removed:
  Kadesh 38, Domesday 200, 428 and 552, Gierke 16 and 84.
- **Footnotes left in the text are notes.** Gierke's introduction (35
  pages, 74 footnotes) printed its notes in the text; Domesday's ten
  single-line notes too; 21 more Domesday references are linked
  ("servus*." on page 55).
- **Stubbs' margin notes** that sat on the text's own lines: those left
  in the text fell from 169 to 46 of 467.

Checked: the quick tests (2,935 in 55 s, back under the minute; they
took 70 s before this plan) and the 167 whole-book tests pass; the
eight EPUBs pass epubcheck with no error or warning; the evaluation
against the Project Gutenberg texts of four books (the scorer of
`docs/specs/evaluation.md`) shows no score falling beyond the plan's
limits. The pages of every rule were compared with their images.

Still wrong, for later plans:

- Some of Gierke's new footnote links go to the wrong note or none
  (pages 31, 36, 50, 109, 147). Before this plan those notes were in the
  text with no links at all.
- Stubbs' text still holds garble from the margin notes beside it on
  some pages (19, 37, 56, 97, 102, 120, 236), most of it as before.
- A book whose contents page is not listed in its `book.toml`
  (`contents_pages`) and whose contents labels are set smaller than
  the text, as Turney's are, would have the labels taken for margin
  notes. Turney's and Haynes' configs list their contents pages.

Decided while the owner was away, each easy to change: pages.json has a
new page kind, `inkless`, so books run before the merge must run again
from the first step, analyze; a page of faint real print is kept when
2 or more of its inkless words are real words; a contents entry of
Domesday ("Statistical Tables") now links to the heading "STATISTICS."
on page 426, the second half of the title "TABLE I. STATISTICS.", one
page after its start.

Asked of the owner: the order to merge, and a look on the Kindle at
`runs/stray-text/` of the main checkout: Haynes after the contents,
Gierke's introduction, and Stubbs' pages with margin notes.

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

## Review of the layout half, task 3.5 and task 4.3

Four reviewers read b3fa355..c45f845. No word was lost without a
record or invented on the eight books. What mattered, all fixed in 15
commits (0006c41 to 0acaf21):

- **Turney's contents page broke.** The new size test of cut-in rows
  took the contents' chapter labels, set smaller than the body on the
  titles' baselines, for margin notes: six labels left their entries.
  Cut-in notes are now not looked for on a page of the config's
  `contents_pages`; Turney's page 10 is as on main and nothing else
  changes. Two other rules were measured and dropped: the labels are as
  small as Stubbs' notes (0.69 of the body's height), and asking for two
  strip words in a row would lose 148 of Stubbs' note words. A book whose
  contents pages are not in its config could still be hit.
- **A heading could be taken into a running head.** A page number
  boxed apart now takes the next row only within 2 pitches; the four
  real cases lie 0.59 to 1.61 pitches below it.
- **Gierke's last introduction page (50) kept its 5 footnotes in the
  body**: its note rows outnumber its text rows. The page's median row
  height is now taken over full-size rows when they are at least a
  quarter of the page's; only page 50 changes.
- A false count in structure §2 (36 regions have the one-line note's
  form, of which 11 change kind), the thresholds table of layout, five
  clauses no test guarded, stale whole-book floors (now Mariéjol 336,
  Domesday 489, Gierke 35 footnote pages; Stubbs at most 51 notes in the
  body), names that clashed with the PDF page size, code written twice,
  docstrings; the inkless warning now also gives the share of known
  words. The known-word limit moved from 0.5 to one third, midway
  between the junk pages (at most 0.17) and Gierke 1 (0.50).

Not taken: an excerpt mixing Gierke's introduction with its body pages,
to guard the page-relative rule outside the unit and whole-book tests,
because the quick tests are already over their minute; a test of one
clause of structure's region kinds that cannot change any kind (the
clause stays); a speck on Gierke 147 that opens a footnote, which needs
a change to margin regions inside a band, for a later plan. Domesday
428's "26—2" was in the text on main too.

After the fixes: ruff and ty pass; pytest 2,910 passed and 6 expected
failures in 79 s, and with 8 threads in 126 s (one run of three by the
fixer ended with one error it did not capture; two reruns and mine
passed); the plan's whole-book tests 15 passed.

## Spec review of the late amendments

A spec reviewer read the amendments made after the first spec review
(layout §3, §6, §8; structure §1, §2, §16, §21; plates §2b; reocr §3,
§8). None makes a rule wrong on the eight books. Fixed in 212111a and
f78158a:

- **Decided while the owner was away:** the condition that keeps a
  short page of faint real print. A share of known words (one third)
  was one word away from keeping Haynes 9, and any number counted as
  known, so a stray digit could keep Haynes 421. A page is now kept
  only when at least 2 of its words without ink are known words of 2
  letters or more. Haynes 9 has 1 ("SP"); Haynes 421 and Haskins 277
  and 278 have none. The inkless pages of the eight books are
  unchanged.
- Layout §6 and structure §21 said the cut-in rule moves no word of
  Turney or Haynes; it would move Turney's contents labels but for
  `contents_pages`, which they now say. Architecture's config table
  names layout's use of the key.
- Smaller: an invented example marked as such, three unit tests listed
  in layout §8, and Gierke's counts measured again after the full-size
  rule (74 footnotes, 5 of them on page 50).

## Task 5.1: the whole-book tests, the EPUBs and the evaluation

At c62dcb1 (the spec fixes above change no output of the eight books):

- `uv run pytest -m whole_book`: 167 passed in 10 min 27 s.
- The eight books in `runs/stray-text/` of the main checkout, in 5 min
  42 s; epubcheck 5.4.0 reports no error and no warning on any.
- The evaluation in `runs/stray-text-final/` (3 min 47 s) against
  `runs/lists-figures-final/`, with the tolerances of the lists-figures
  plan (the evaluation spec gives none): no score falls beyond them.
  The one fall is Mariéjol's paragraph recall, 0.765 to 0.764.

| book | measure | before | after |
|---|---|---|---|
| Stubbs | body word error rate | 0.033 | 0.029 |
| Stubbs | margin notes as margin notes | 291 | 413 |
| Stubbs | margin notes left in the body | 169 | 46 |
| Stubbs | margin notes missing | 7 | 8 |
| Stubbs | paragraph precision | 0.818 | 0.825 |
| Domesday | notes as notes | 1,705 | 1,715 |
| Domesday | notes with the right reference | 1,277 | 1,307 |
| Domesday | notes left in the body | 24 | 14 |
| Domesday | paragraph precision | 0.861 | 0.884 |
| Mariéjol | notes as notes | 1,154 | 1,160 |
| Mariéjol | notes left in the body | 231 | 225 |
| Haskins | every score | | unchanged |

Gierke, not an evaluation book, counted from its blocks: notes 302 to
373, of which on the introduction's pages 1 to 62; references in the
text 208 to 274; notes without a reference 94 to 99; quotes 24 to 0
(task 5.2 looks at why).

## Task 5.2: the checks by eye

A subagent compared the Markdown of the eight books with the page
images, on the pages of each rule.

Right: the four inkless pages are gone and the text around them whole;
the running heads of Kadesh 38, Domesday 200 and 552, Gierke 16 and 84
are gone; the footnotes of Gierke 15, 16, 30 and 146 and the one-line
notes of Domesday 55, 163, 174, 185, 278 and 303 are notes, "servus*"
linked; Stubbs' notes on pages 19, 37, 56, 97, 102, 120, 177 and 236
are margin notes, whole on 19, 97 and 120; Turney's contents is as on
main. Gierke's 24 quote blocks of main were all footnotes and are notes
now; no real quotation was lost.

Made worse by this plan, and fixed (742590a to de04d09):

- **Domesday 428** lost its heading "AVERAGES.", glued to the table of
  page 427, and kept its signature mark "26—2". Now layout makes the
  table a band, so the body of the page is that one line; structure §14
  lets a line of a page with fewer than 5 body lines be flush left
  between the sides of the body and the band, and §4 takes a signature
  mark from the line above the lowest when the lowest is nothing to
  remove. Domesday 426's "STATISTICS." became a heading by the same
  rule.
- **Domesday 552**, an index page, had its two columns broken at the
  bottom. On a page whose every row is small, body runs now end where a
  band's runs may (layout §3, steps 4 and 5).
- **Gierke 38**'s signature mark "M. c" (already a junk quote on main)
  was a footnote with a reference. §4 now also takes a capital with a
  full stop followed far to the right by a word. Signature marks are
  also removed on Domesday 234 and Gierke 54, 70 and 246.

These fixes change no other page of the eight books for the worse; the
pages that change were each looked at.

**Still wrong**, for later plans:

- **Gierke's footnote links.** The introduction's notes are notes, but
  some references go to the wrong one: on page 36 "incorporation²"
  links note 3 and note 2 has none; on 31 note 1 is cut in two at
  "(2)" and two references link one note too early; on 50, 109 and 147
  a reference is not linked. Before this plan these notes were quotes
  in the text with no links at all.
- **Stubbs' body** still holds junk of the margin notes beside it, most
  of it as on main: "an epoch v which" (19), "they were j-j^ too anc j
  earnest" (37), "chaplains, r and" (56), a scrambled line order on 97,
  a note cut in two on 102 ("Coronation of the youpg" in the body), "re_"
  on 120, garble on 236.
- Pencil specks become margin notes inside footnotes on Gierke 36 and
  147, and a margin note "^" on Gierke 30.

## Task 5.3 and the last fixes

The last review's findings were fixed (bed681f to bbde92c): names and
docstrings in layout, one test case per guard of the signature-mark
rule, comments that say a threshold was chosen. The eight books' lines
and blocks are byte-identical before and after.

The quick tests took 80 s: the session fixture ran the 24 excerpts as
threads of one process, all waiting on the one PDFium thread. Each
excerpt now runs as its own process, 12 at a time (ca41c8e); three runs
before, 79.6, 80.2 and 80.3 s, after, 55.5, 55.8 and 55.6 s. No test was
dropped.

Final: ruff, ty and `uv lock --check` pass; pytest 2,935 passed, 6
expected failures, in 55 s (100 s with 8 threads); `pytest -m
whole_book` 167 passed in 10 min 18 s; the eight EPUBs rebuilt in
`runs/stray-text/` pass epubcheck 5.4.0 with no error or warning. The
evaluation run again differs from task 5.1's in one score: Domesday's
paragraph precision, 0.884 to 0.883, within the limit of 0.005.

The whole-book test of Domesday's contents links failed at 24 against
23: since b12097e "STATISTICS." on page 426 is a heading, and the entry
"Statistical Tables" links to it (ratio 0.71). Accepted, and the spec
and test changed (85bd57b, 0a5fceb).

## For whoever next revises a skill or writes a plan

- The plan's thresholds came from simulations of the investigations;
  work package 1 changed six of them when it measured them with
  layout's own code. A plan built on simulated numbers should say they
  are provisional and point to the spec for the real ones, as this one
  did after work package 1.
- Streams limited to their own files twice needed a test file of
  another stream (`tests/test_layout.py`, `tests/test_excerpts.py`) when
  a rule changed an excerpt's expected output. A plan should list the
  excerpt expectations a rule may change as files the stream may touch.
- Two fixes made in the first review round broke things the checks by
  eye then found (Domesday 428 and 552): the page-number rule's spec
  named the pages it changes, but nobody looked at the blocks of those
  pages until task 5.2. A rule's own task should look at the blocks of
  every page it changes, not only count them.
- Rules in layout that structure repeats (the band's size, the one-line
  note) were specified twice and drifted twice; the stage boundary made
  it necessary, and both specs now point to each other.
