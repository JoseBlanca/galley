# Report: paragraphs cut by notes, and a local vision model

## Summary

The plan is done on branch `plan/notes-vision`, on 19 November 2026,
and waits for the owner's order to merge it into `main`. The EPUBs are
in `runs/notes-vision/<folder>/` of the main checkout; Kadesh read with
the vision model is in `runs/notes-vision/battleofkadeshst00breauoft-correct/`.

What changed for a reader:

- **Paragraphs are no longer cut at a page break by notes.** A rule
  kept a paragraph that opens with a number ("1. Of the three…") from
  running on to the next page, because the number looked like a note's.
  Kadesh (`battleofkadeshst00breauoft`) now reads "…collated with the
  original of the Sallier Papyrus…" as one paragraph, with the notes
  after it; Domesday (`domesdaybook00maituoft`) "No doubt, the medieval
  sheep" likewise.
- **Stubbs (`earlyplantagenet01stub`)**: "aggressive" is whole, and the
  margin note "First invasion by the Scots." no longer sits inside "David
  had taken Newcastle". Stubbs' margin notes left in the text fell from
  46 to 36.
- **The correct stage exists**, off by default. With `correct = true`
  in a book's `book.toml`, galley asks a vision model running in LM
  Studio on this machine (Qwen 3.6 35B-A3B; no text leaves the machine)
  to read each page image, and replaces galley's word with the model's
  where the two line up and differ. Every change is written to
  `edits/correct.jsonl`. On six Kadesh pages transcribed by hand, wrong
  words per 100 fall from 2.7 to 1.4 in the text and from 26.8 to 5.5 in
  the notes; the whole book takes about 8 minutes.

Checked: all tests (3,199 quick ones, in 75 s, over the minute; 159 on
whole books); the seven EPUBs pass epubcheck with no error or warning;
the evaluation against the Project Gutenberg texts of Haskins, Stubbs
and Domesday: every score that changed got better. The joined
paragraphs, the Stubbs lines and 20 random edits of the correct stage
were checked on the page images (19 right, 1 half right).

Still wrong:

- **About 1 word in 300 that the correct stage writes is wrong but looks
  right**: 11 on the six pages, among them "orientalis" for the printed
  "orientalists" twice. A dictionary rule against such cuts was measured
  and dropped: it refused 12 right edits for 1 wrong one.
- Combining the scan's text with Tesseract was measured and not built:
  even a perfect choice between them would leave 12 wrong words per 100
  in Kadesh's notes.
- The quick tests take 75 s.

**Decision asked of the owner** (the spec's open point 1): how to use
the correct stage, given the fluent wrong words.

- (a) On, as it is: about 37 such words in Kadesh, not flagged.
- (b) On, with the second reading by Qwen 3.6 27B
  (`correct_second_model` in `book.toml`): about 20 more minutes a run;
  on the six pages it flags 19 of the 21 wrong note edits and 38 of the
  308 right ones, so about 150 flagged edits to look at in Kadesh.
- (c) Off.

Recommended: (b) for Kadesh; off for books whose OCR is already good,
until a second book is measured.

Also asked: the merge, and a look on the Kindle at
`runs/notes-vision/battleofkadeshst00breauoft-correct/book.epub` beside
`runs/notes-vision/battleofkadeshst00breauoft/book.epub`, pages 11 to 13
and their notes.


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

## Review of the correct stage

Two reviewers read 1d9c16d..700d652. What mattered, all fixed (f9f53f4
to de66c8d), spec first where a rule changed:

- **Edits lost printed words**, about 20 on Kadesh ("pp. 542, 543." to
  "pp, 543.)"): a galley word holding two printed words was replaced by
  one of the model's. No replacement now when galley's word has more
  separators or digits than the model's; where galley glued two words,
  the edit takes both of the model's. The last case, "1%The" to "The"
  (page 53, a misread note marker), is refused by a rule that keeps any
  piece of digits and marker signs glued to a word.
- **Closing quotes and a note marker dropped** ("him.”’!7" to "him"):
  the set of punctuation before a glued marker is now the spec's.
- **Insertions repeating words** a note already held: refused.
- **Nonsense replacements** where galley's reading order was wrong (page
  14, "his" to "Mashawasha"): a block part whose unequal pairs average
  under 0.3 alike gets no edit (page 14's measure 0.00 to 0.19; the
  reference pages 0.36 to 0.93).
- **The page images could go through a proxy** set on the machine: the
  stage now ignores proxies and redirects, tested with `http_proxy` set.
- **The excerpt test passed while the stage invented about 230 words**:
  it now pins the 475 edits, literal edits and page order, which found a
  real bug (the edits file was not in page order). Other unguarded
  rules are pinned.

Kadesh's third run with the final rules: 1,029 edits on 44 pages in
666 s; on the six reference pages 1.4 wrong words per 100 in the body
and 5.5 in the notes (2.7 and 26.8 without the stage); 11 fluent wrong
words; no edit drops a printed word (5 replacements with fewer words
are junk inside a word, "P#@igns" to "campaigns"). pytest 3,199 passed
in 76 s, over the minute.

During the review fixes the agent unloaded the Qwen 27B model in LM
Studio, which another session may have loaded; it was told not to.

## Work package 5: the runs and the checks by eye

At 66e7bf7 plus the fix of "1%The" (de66c8d): pytest 3,199 passed in 75 s,
`pytest -m whole_book` 159 passed; the seven EPUBs in
`runs/notes-vision/` pass epubcheck; Kadesh with `correct = true` in
488 s, 1,027 edits, 1.4 and 5.5 wrong words per 100 on the reference
pages, 11 fluent wrong words, no printed word dropped. The evaluation,
copied to `runs/notes-vision-final/`, against `runs/ocr-redo-final/`:
Stubbs' margin notes as margin notes 413 to 423, left in the body 46 to
36, its body error rate 0.0251 to 0.0248; Domesday's paragraph precision
0.8825 to 0.8837; Haskins one split word fewer. Checked by eye: Kadesh
pages 11 to 13, Domesday 467 to 468, Stubbs pages 24 and 34, right; 20
random edits, 19 right and 1 half right ("Neb!" to "Nebi!", printed
"Nebi").

A rule against cut-short words ("orientalists" to "orientalis") was
measured: refuse a replacement when galley's word is in the dictionary
and the model's is not. Tesseract's English list lacks "orientalists"
and "inscriptional" and has galley's misreadings ("rowe", "pare"), so
the rule caught none of its targets and refused 12 right edits for 1
wrong one on the six pages. Not built.
