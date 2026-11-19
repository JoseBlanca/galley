# Report: unlinked notes and note links

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
