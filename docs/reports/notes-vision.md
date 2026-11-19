# Report: paragraphs cut by notes, and a local vision model

The work report of `docs/plans/notes-vision.md`, for the owner. Started on
19 November 2026, at main df72ba4.

## Work package 2: the measurement

Done; the report is `docs/reports/notes-vision-measure.md` (c501378).
On 6 Kadesh pages transcribed by eye (1,975 body words, 1,356 note
words), wrong words per 100: galley with redo 2.0 in the body and 26.5
in the notes; the best any combination of the text layer and Tesseract
could do, 0.5 and 12.3, and a simple combination 1.4 and 24.4; the
vision model Qwen 3.6 35B-A3B reading the whole page 0.9 and 2.8, in
12.8 s a page, and merged with galley's words 0.7 and 3.4. Its risk:
about 1 word in 300 is wrong but looks right ("Borchardt" for
"Brugsch"). Combining the layer and Tesseract is not built; work
packages 3 and 4 build the correct stage with that model, reading whole
pages, merged word by word, off by default.

## Work package 1: paragraphs cut by notes, and Stubbs

Merged: 4338e8e (specs), e081685 (code and tests). pytest 3,108 passed
in 69 s; `pytest -m whole_book` 159 passed.

- **Paragraphs cut at a page break.** The notes were not the cause:
  structure §16 never let a block run on to the next page when its
  first word looked like a note marker, and Kadesh numbers its
  paragraphs "1.", "3." with the same digits as its notes. Such a block
  now runs on when it is in body-size type and its page's last line does
  not end a sentence; the notes then follow the joined paragraph.
  Paragraphs ending without punctuation right before a note block:
  Kadesh 7 to 5, Domesday 5 to 4, Stubbs 1, the others 0; the 10 left
  were each checked on the page image, and none is a cut at a page break.
  Not fixed: Domesday page 473, where a line of two notes stands in the
  body at full height (in the spec). New excerpt `domesday_run_on`.
- **Stubbs "aggres* sive"**: a hyphen read as "*". The halves are joined
  when the word list knows the whole word, and the "*" is recorded with a
  new removal reason, `misread_hyphen`, which the fidelity check
  requires. On the seven books it joins "aggressive" and Haskins'
  "pilgrims" (page 226).
- **Stubbs "p by 5*invasion"**: a margin note 7.9 pt from the text, under
  the 8 pt gap. A row whose strip words are in small type is now cut at
  7.8 pt; 11 Stubbs pages change, all margin-note words; at 7.5 pt or
  without the type test body words move. Stubbs' margin notes 434 to 443.

## Review of work package 1

Two reviewers (spec and fidelity; tests and conventions) ran the seven
books before and after: no word lost, duplicated, reordered or invented;
the run-on joins only three real sentences cut at a page break (Kadesh
11 to 12 and 12 to 13, Domesday 467 to 468), the misread-hyphen join
only "aggressive" and "pilgrims". Fixed (af08956 to 235ad95): a chain of
two joins over a sign that would have stopped structure on a whole book
(no book has one); the layout spec claimed Stubbs page 102's note leaves
the body whole, but "Coronation" stays; tests that passed for the wrong
reason, or guarded nothing of the 7.8 pt cut's size test and of the
fidelity check's sign join; a constant written twice. pytest 3,117
passed in 73 s; the Stubbs and Haskins whole-book tests 49 passed.

## Work packages 3 and 4: the correct stage

Merged: 7170489 and e290a0b (`docs/specs/correct.md` and the
architecture's parts on correct, edits and the config), 8350806 (the
stage: `galley2epub correct`, run by `run` when `correct = true`;
markdown applies its edits; config keys `correct_model`,
`correct_server`, localhost only, and `correct_second_model`; a pytest
marker `vision_model`, excluded by default), 69a46a2 (Kadesh's numbers).

Kadesh with `correct = true` (Qwen 3.6 35B-A3B through LM Studio): 1,218
edits on 44 text pages in 474 s, the machine shared with other
sessions. On the six reference pages, wrong words per 100:

| | body | notes |
|---|---|---|
| before correct | 2.7 | 26.8 |
| after correct | 1.3 | 5.5 |
| the measurement's estimate | 0.7 | 3.4 |

The gap to the estimate is a guard added while building: no
replacement when the two words are less than 0.3 alike. It costs the
notes 3.8 to 5.3 on the recorded answers and removes 3 wrong words that
read as real ("Borchardt" for "Brugsch" twice, "Med." for "Hist.");
kept, since a fluent wrong word is worse than visible junk. Fluent wrong
words left: 11 in 3,331, about 1 in 300. The optional second reading
(Qwen 3.6 27B) flags 18 of the 21 wrong note edits and 27 of 324 right
ones.

After the merge pytest 3,167 passed in 82 s: the stage's excerpt test
takes 12.5 s; the review looks at it.
