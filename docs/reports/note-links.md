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
