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
