# Plan: unlinked notes out of the text, note links from the vision model

The owner read Kadesh (`battleofkadeshst00breauoft`) on 19 November 2026
and found footnotes standing between its paragraphs: notes whose
reference in the text is not linked (142 of Kadesh's 183) are shown
where they were printed. The owner chose, the same day, to move such
notes to the end of their chapter, and to go on with linking more of
them from the vision model's reading of the small raised numbers.
Dated 19 November 2026. State: approved; under way.

## 1. Unlinked notes at the end of the chapter

A footnote with no linked reference goes, in book.md and the EPUB, to
the end of its chapter (the section that ends at the next level-1 or
level-2 heading, or the book's end), under a heading "Notes", in the
order printed, each still with its marker and its page. A book's
endnote section and notes already linked do not change. Spec first
(markdown and structure, wherever the placement of unreferenced notes
is said; the owner's decision, 19 November 2026), then code and tests;
counts per book of notes moved; the seven books' EPUBs through
epubcheck.

- [x] 1.1 Spec, code, tests, counts.
- [x] Review of work package 1.

## 2. A hyphenated word in the correct stage

The correct stage replaced the second half of "cam- P#@igns" with
"campaigns" and left "cam-" (Kadesh page 8). When galley's word is the
second half of a word split over a line end, the edit must cover both
halves. Spec first (`docs/specs/correct.md`), a test that fails first,
and a count of such cases in Kadesh's edits.

- [x] 2.1 Spec, code, test, count.

## 3. Note links from the vision model

Measure first, on the six reference pages of the notes-vision plan
(`tmp/measure/` of that plan, copied): ask the 35B model to give, for
each note reference it sees in the text, its number and the word before
it; match them with galley's words and notes. Count notes linked that
are not linked now, links to the wrong note, and time. If it links more
than half of the unlinked notes with under 1 wrong link in 20, write the
rule into the correct spec and build it; otherwise report and stop.

- [x] 3.1 The measurement.
- [x] 3.1b The same prompt on six other Kadesh pages, their references
  read from the images and committed; build only if the twelve pages
  together pass the bar.
- [x] 3.2 The rule and its code, if 3.1 says so.
- [x] Review of work packages 2 and 3.

## 4. The EPUBs

- [ ] 4.1 All checks, `pytest -m whole_book`, the seven EPUBs in
  `runs/note-links/` through epubcheck, Kadesh with `correct = true` and
  the second reading, the doubtful edits checked on the page images as
  before (owner edits), and the pages of each change checked by eye.
