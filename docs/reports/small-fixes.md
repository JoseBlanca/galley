# Report: three faults left after the note-links plan

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
