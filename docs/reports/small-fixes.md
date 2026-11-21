# Report: three faults left after the note-links plan

## Summary

The plan is done on branch `plan/small-fixes`, on 21 November 2026, and
waits for the owner's order to merge. The EPUBs are in
`runs/small-fixes/<folder>/`.

- Kadesh (`battleofkadeshst00breauoft`): the quoted inscription on page
  39 is no longer a heading, so the unlinked notes no longer gather
  there; galley's own note links on pages 9 and 10 go to the right notes
  (43 links, 5 changed, all checked on the images).
- A note link added by the vision model takes the place of the sign the
  OCR read for the note's number ("soldiers;™" becomes "soldiers;" with
  the reference).
- The quick tests take 61 to 62 s on a quiet machine, from 81 s.

Checked: all tests, the 159 whole-book tests, the seven EPUBs through
epubcheck; the evaluation unchanged. Two reviewers found no lost word or
wrong link on the seven books; their findings (guards for other books,
tests, names) are fixed.

For the owner. Started on 21 November 2026.

## Tasks 1.1 and 2.1

Merged: 46d8016, 0d7fcb5 (Kadesh page 39: a line right below a line
Tesseract read poorly cannot become a heading by its spacing alone;
only this line changes on the seven books; Kadesh's headings are those
of pages 8 and 66); 2ae1f27, 9cb16a1 (an opening single quote after a
letter is a reference candidate; a footnote without a number between
two numbered notes takes the number of its place: Kadesh links 41 to
43, five links changed, all right on the images, nothing changed on the
other six books); e063930, 99dcd17 (a side effect in the correct stage:
a reference galley already links counted twice in the page-order rule
and refused a whole page; now counted once).

Kadesh run with the correct stage, note links and the second reading at
the note-links code (`runs/note-links/battleofkadeshst00breauoft-correct2/`):
1,090 edits, 40 links, all right; 177 doubtful edits checked on the
images, 61 wrong undone in `edits/owner.jsonl`; epubcheck clean.

## Tasks 3b.1 and 3.1

Merged: 20eb634, 1c5880e (a vision-model link takes the place of a sign
the OCR read for the note's number, keeping real punctuation:
"soldiers;™" becomes "soldiers;" with the reference; 4 of Kadesh's 40
links change, pages 15, 20, 37, 59) and 61eeed7 (the quick tests: the
excerpt runs start at the beginning of the session while unit tests
run, the correct stage's excerpt tests share one run, two Tesseract
tests read in parallel; no check dropped). Three timings on a quiet
machine: 81.2, 80.9, 81.0 s before; 62.0, 63.5, 63.8 s after; with 8
threads 131 s to 114 s.

## Review and the end

Two reviewers read 0c64405..f977c03. No lost word, invented text or
wrong link on the seven books; every changed link and heading right on
the images. Fixed (3fa5b38 to 2079590): a real sign ("50%") could be
taken for a misread reference, now only ™, ® and ^ are; a "‘" read for a
closing quote could be replaced by a link, now kept only when it links
more of the page's notes; five unguarded branches; names; work done
when links are off; a missing excerpt PDF failing every test. Then:
pytest 3,290 passed in 61.3, 61.4, 62.5 s; `pytest -m whole_book` 159
passed; the seven EPUBs in `runs/small-fixes/` pass epubcheck; the
evaluation in `runs/small-fixes-final/` equals `runs/note-links-final/`.
