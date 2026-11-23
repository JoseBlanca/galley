# Report: the correct stage on a second book

For the owner. Started on 21 November 2026, at main 5e96e12.

## Summary

Done on branch `plan/second-book` (fb7addf to a3edb76), and waiting for
the owner's order to merge.

- **The correct stage on Domesday** (`domesdaybook00maituoft`), a book
  with good OCR: on six pages read by eye (2,485 words, committed in
  `tests/fixtures/expected/domesday_reference/`), wrong words in the
  English body fall from 6 to 3 of 1,417, in the Latin page from 32 to
  13 of 469, in the footnotes from 23 to 10 of 371; the table of page 426
  gets worse (13 to 18). Of 77 edits, 23 are wrong, 12 of them turning a
  right word wrong; the second reading marks 11 edits, 9 of them wrong,
  and misses the body's wrong ones. Recommended in `docs/specs/correct.md`
  §16: off for a book like this. The whole book would take about 3 hours,
  7 with the second reading.
- **Kadesh's pages without links**: 3 of the 13 now get them, 13 more
  link edits, all right against the reference and on the images; the
  others are refused because galley split or joined their notes, or the
  model left a reference out. A check that compared the model's numbers
  with galley's markers was dropped: it caught none of the earlier wrong
  links and refused right ones.
- A reviewer found no wrong link and no lost text; its three small
  findings are fixed (a3edb76). pytest 3,293 passed.

Not done: the Kadesh EPUB with the new links. The run in
`runs/second-book/battleofkadeshst00breauoft-correct/` stopped when the
GPU ran out of memory while the owner's other program was using the 27B
model; it needs LM Studio free for about 35 minutes.
