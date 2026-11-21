# Report: unlinked notes and note links

## Summary

The plan is done on branch `plan/note-links`, on 20 November 2026, and
waits for the owner's order to merge. The EPUBs are in
`runs/note-links/<folder>/` of the main checkout; Kadesh with the vision
model (correct stage and note links, no second reading) is in
`runs/note-links/battleofkadeshst00breauoft-correct/`.

- **Unlinked footnotes are out of the text**, at the end of their
  chapter under "Notes", a heading kept out of the table of contents:
  Kadesh 142 notes, Domesday 323, the other books 0 to 8. On Kadesh this
  is far from where they were printed: the book has one real chapter,
  and a quoted inscription on page 39 taken for a heading collects the
  notes of pages 8 to 38.
- **The vision model links notes** (`correct_links`, on with the correct
  stage): on Kadesh notes with a reference rise from 41 to 76 of 183;
  every one of the 40 new links was checked on the page images and all
  are right. A first version, tuned on twelve pages, linked 111 but
  with about 1 in 3 wrong outside them; rules on the order of the
  numbers removed those.
- **"cam- P#@igns" now reads "campaigns"**, and "Dindorf-Müller" keeps
  its hyphen.

Checked: pytest 3,262 passed (144 s on a busy machine); `pytest -m
whole_book` 159 passed; the eight EPUBs pass epubcheck; the evaluation
of Haskins, Stubbs and Domesday did not change.

Still wrong: galley's own links (not the model's) are wrong three times
on Kadesh pages 9 and 10; Kadesh's page-39 heading; the quick tests take
over a minute. Not done: Kadesh with the second reading and the check of
its doubtful edits, which needs the owner's Qwen 27B model free for
about 40 minutes.

The work report of `docs/plans/note-links.md`, for the owner. Started on
19 November 2026, at main 8c5f8b2.

## Work package 1: unlinked notes at the end of the chapter

Merged: b646445 (structure §36, architecture §9, §13, §17), 41fd6da.
A footnote with no linked reference goes to the end of its chapter
under "Notes", a heading one level below the chapter's, marked
`.unlisted` so that it stays out of the EPUB's table of contents
(Pandoc 3.14). The fidelity check reads that heading as no word of the
book.

| book | unlinked footnotes moved | "Notes" headings |
|---|---|---|
| battleofkadeshst00breauoft | 142 | 3 |
| domesdaybook00maituoft | 323 | 23 |
| politicaltheorie00gieruoft | 8 | 5 |
| normansineuropea00hask | 2 | 2 |
| earlyplantagenet01stub | 2 | 2 |
| turney | 1 | 1 |
| haynes | 0 | 0 |

The seven EPUBs pass epubcheck. Notes of a page whose chapter heading
stands below its first line go to the new chapter (4 notes in Kadesh,
12 in Domesday). On Kadesh a line of page 39 taken for a heading
collects the unlinked notes of pages 8 to 38 (74). `docs/specs/evaluation.md`
still says an unlinked note follows its page; task 4.1 corrects it.

## Work package 2: a split word in the correct stage

Merged: 0fecbdb (spec), 33442c3. When the word before galley's word ends
in a hyphen and pairs with no word of the model's, the edit replaces
both halves: "cam- P#@igns" becomes "campaigns". 3 of Kadesh's 1,050
edits were of this kind; 2 are now covered, the third (page 11) has its
first half on page 10.

## Task 3.1: note links from the vision model, first measurement

The note references of Kadesh pages 8, 9, 11, 15, 27 and 29 were read
from the page images and committed (ac488a2,
`tests/fixtures/expected/kadesh_reference/note_references.json`): 27
references, 24 with a note of their own in galley. Galley links 6 of
them, 2 right and 4 to the wrong note. Asking the 35B model to copy the
page's text with each reference as "[n]" proposes 13 links, all right:
9 of the 18 unlinked notes linked, 3 of galley's 4 wrong links put
right, 2 of 2 right links kept; 31 s a page on average. That is exactly
half, the plan's bar, on 13 links, too few to show a wrong rate under 1
in 20. Decided: measure the same prompt on six other Kadesh pages
before building (task 3.1b).

## Tasks 3.1b and 3.2: note links from the vision model

Six more Kadesh pages read from the images (bf8568b; 62 references on
twelve pages). On the twelve pages the first prompt made 25 links, none
wrong, but linked only 20 of 43 unlinked notes, under the plan's bar of
half: the model followed the answer format on about half the pages.
Decided: a link that is always right is worth having, so the bar became
"at least 20 links, at most 1 wrong in 20". A second prompt without an
example line, accepting raised digits, made 32 links with none wrong
(the first, read more loosely, 36 with 1 wrong); the second is built.

Built (2fc2482, b4e57b4, 5567153): a link is an edit of
`edits/correct.jsonl` whose new text ends with a link to the note;
markdown makes it a reference after the word. On whole Kadesh, notes
with a reference rise from 41 to 111 of 183; on the twelve reference
pages all 27 new links go to the right note, and galley's wrong links
fall from 6 to 4. 11 links are refused and logged (the word changed by
another edit, two links to one note, and others). The 52 links outside
the twelve pages are not checked yet. The run took 3,808 s, against
474 s without links, with the owner's other model generating at the
same time: links need a second request on each page where a note
starts.

Open: a link cannot yet be rejected for good (an owner edit cannot
remove a reference, and the stage proposes it again on its next run).

## Review of work packages 1 to 3

A spec reviewer and a code reviewer read 8c5f8b2..c0cbf68. Every note
is still written exactly once in Kadesh, Domesday and Gierke. What
mattered, fixed in 637dbcf to eb843d5:

- **Wrong note links outside the reference pages**: 8 of 27 checked on
  the page images were wrong (page 31's five links one note too far,
  page 21 two, page 45 a link after the wrong word). The rules had been
  tuned on the twelve pages. New rules: the k-th reference the model
  marks on a page must go to the page's k-th footnote; the numbers must
  rise and agree with galley's markers; galley's word may differ from
  the model's by one character at most; the edit keeps the model's
  number. A new whole-Kadesh run was then checked link by link on the
  images: with the order rules alone 68 links, 7 wrong; with the k-th
  rule as well 40 links, all right. Notes with a reference: 41 to 76 of
  183. A new key, `correct_links`, turns links off; it is on by default
  with `correct`. The model's answers vary between runs at temperature
  0, so "0 wrong" is one run's result.
- The link request went to endnote pages too (93 pages of Gierke,
  about 76 minutes for nothing): now only pages where a footnote starts.
- A printed closing quote could become a reference's text and vanish
  from the EPUB: kept in the word now.
- "DINDORF- MÜLLER" became "Dindorfmüller": the hyphen of two capital
  halves now stays ("Dindorf-Müller").
- Two unguarded rules, an unclear error for a note referenced twice,
  and spec mistakes.

pytest 3,262 passed.

## Task 4.1: the runs

8dab549 corrects the evaluation spec (an unlinked note goes to its
chapter's end); galley-eval needed no code change. All checks pass;
`pytest -m whole_book` 159 passed; the seven books and Kadesh with the
model pass epubcheck; the evaluation in `runs/note-links-final/` is the
same as `runs/notes-vision-final/`. Checked by eye: the "Notes" heading
and the moved notes on Kadesh pages 8 to 13, the model's 4 links there
right; Domesday's chapter "The Serfs" with its two unlinked notes before
the next chapter.
