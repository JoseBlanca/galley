# Report: reading a badly OCRed book again, and Stubbs' letter fragments

The work report of `docs/plans/ocr-redo.md`, written as the work goes,
for the owner. Started on 19 November 2026.

## Before the first task

The plan was written on 19 November 2026 from two investigations at
main 9292b17; the owner said to go on without waiting. Tesseract,
Pandoc and epubcheck are installed. The investigations' notes and
scripts are in `tmp/investigation/` of the plan's worktree (not
committed).

What the investigations found that shaped the plan:

- Kadesh (`battleofkadeshst00breauoft`) is the one book of the seven
  whose layer Tesseract beats: on 44 text pages the share of known
  words is 0.903 for the layer and 0.922 for Tesseract, better by more
  than 0.03 on 12 pages and worse on none. On 10 pages each of the
  other books, the two are within 0.02.
- A plain redo loses Kadesh's note links (31 linked with the layer, 2
  with Tesseract) and adds 13 junk headings from hieroglyph rows; the
  plan adds work package 3 for both.
- Stubbs' stray characters are pieces of letters the layer split off as
  words, not the ends of note lines.

## Work package 1: specs, the excerpt, titles and Mariéjol

Done in three commits: 00e4647 (specs: architecture, extract §9,
structure §34 and §35, glossary, reocr), c07a110 (the excerpt
`kadesh_redo`, Kadesh pages 8 to 16, 32 and 34, with 6 tests expected to
fail until their tasks), af90d25 (titles and authors in the whole-book
configs; Mariéjol out of the whole-book tests and the evaluation, its
two excerpts still cut). pytest: 2,936 passed, 12 expected failures, in
57 s. The session was cut once by an editor restart; the agent resumed
from its commits.

Rules settled, measured on whole Kadesh and the seven books:

- **Note references under redo**, in extract: a Tesseract word takes the
  layer's reference when the layer word under it (overlapping by half
  in both directions, one to one, as many letters) ends in a glued
  reference and the Tesseract word has no digit. Kadesh: 57 words
  changed, 56 at a printed reference; linked notes 2 to 34 (31 with the
  layer alone).
- **Junk headings under redo**, in structure: a line of Tesseract's
  words with a median confidence below 60 is never a heading.
- **Letter fragments**, in structure: gated per book by the share of
  pages that have one (at least 0.15); Stubbs 0.410 with 251 fragments,
  every other book at most 0.030. Lines shortened by a cut-in note,
  the plan's first idea, took real words in Domesday and Gierke.

Reviewer findings not taken: a whole-book floor of 34 linked notes (31
is kept, and a count below 34 must be explained); asking the owner
about junk Tesseract lines, which stay paragraphs as the layer's junk
does today.

## Work package 4: Stubbs' letter fragments

Merged: 95bd376 (the rule, `structure/_fragments.py`, a new removal
reason, a survey field saying whether the book has fragments) and
c8d1617 (whole-book tests). On the whole books it removes 251 fragments
from Stubbs (`earlyplantagenet01stub`) and none from Haskins, Domesday,
Kadesh, Gierke, Turney or Haynes. Twenty of the 251, drawn at random,
were checked on the page images at 250 dpi: all are pieces of a letter
or of a comma. The four Stubbs excerpts lose 20 fragments, each checked
on its image. pytest: 2,962 passed, 12 expected failures; the plan's
whole-book tests of this work package: 7 passed.

## Work package 2: redo in analyze and extract

Merged: 5da0f3c (analyze accepts redo and marks text pages `ocr`; the
command stops before analyze or extract when Tesseract is missing),
9464243 (extract reads `ocr` pages with Tesseract, and a page where
Tesseract finds no word keeps the layer's; Kadesh's whole-book config
uses redo and leaves out page 74, the library's card pocket), 57af8f1
(the excerpt's excluded region moved to where Tesseract boxes page 0's
"81").

Kadesh's body, share of unknown words (words of 2 letters or more): the
layer 0.0587 (940 of 16,020), redo 0.0570 (973 of 17,067); in the
paragraphs 0.0543 to 0.0517; in the notes 0.173 to 0.126. Redo reads
1,047 more words.

**Not met yet**: 3 of Kadesh's 19 whole-book tests fail under redo, and
go to work package 3. Tesseract misreads the notes' own markers ("Sin"
for "⁵In"), so pages 9, 25, 27, 33, 41 and 50 lose their footnotes
(pages with footnotes 40 to 35), and on pages 9 and 25 two note columns
merge into one line; Tesseract reads the map caption "MAP III." as
"ILL." and misses "MAP V". Work package 3 takes the notes' markers from
the layer as it does the references in the text.

After the merge: ruff and ty pass; pytest 2,979 passed, 8 expected
failures, in 73 s, over the minute: two excerpt tests run Tesseract
(about 6 s each). Task 5.1 looks at it.
