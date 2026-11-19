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

## Review of work packages 1, 2 and 4

Three reviewers (spec; fidelity and tests; conventions) read
9292b17..1f4e9fc. The one finding that mattered: **under redo, printed
lines were lost without a record.** Tesseract skips some lines the layer
has (Kadesh pages 11, 52, 53, and the caption "MAP V"), and extract
kept only Tesseract's words. Decided and fixed in work package 3 (below):
a layer word that no Tesseract word covers is kept in its place.
Letter fragments: 251 on Stubbs, 7 of the riskiest checked again on the
images, all pieces of letters. The smaller findings (stale wording in
the command module, a second letter-count helper, a stale count of
Kadesh's text pages, excluded regions drawn on the layer's boxes, which
under redo can miss a word Tesseract places elsewhere) are fixed after
the review of work package 3.

## Work package 3: notes, headings and captions under redo, and lost lines

Commits 3c1fe42 to 968b83b, spec commits first. On whole Kadesh with
redo, against the layer:

| | layer | redo before | redo now |
|---|---|---|---|
| linked notes | 31 | 2 | 42 |
| headings | 3 | 15 | 3 (pages 8, 39, 66) |
| pages with footnotes | 40 | 35 | 42 |

- Note references: a Tesseract word takes the layer's reference or
  caption numeral under it (61 words).
- Footnotes: they were lost not through their markers but because
  Tesseract boxes some words as tall as their line, so a note's type no
  longer looked small (page 9's notes 9.12 pt against a body of 7.92).
  Each Tesseract word now takes the height of the layer word under it.
- Junk headings: a line at least half of Tesseract's words is judged on
  those, and a median confidence below 60 keeps it from being a heading.
- **Lost lines:** a layer word that no Tesseract word covers is kept,
  after the layer's boxes are shifted by the page's offset from
  Tesseract's; 79 words kept on the book, 55 of them printed text, the
  rest junk the layer had. Pages 9, 11, 15, 52 and 53 regain their lines.
- Map captions: the layer's numeral is taken after "MAP", "figure" or
  "plate" when Tesseract's has no digit ("Y." for "V.").

Not done: on page 25 Tesseract joins two footnote columns into one line,
and that note stays merged. `pytest -m whole_book -k kadesh`: 22 passed;
pytest 3,015 passed, 6 expected failures, in 78 s.

## Review of work package 3

Three reviewers read 1f4e9fc..968b83b and ran whole Kadesh with redo.
What mattered, all fixed (353817d to 3b0c8e2; the redo rules now live in
`extract/_redo.py`, and the caption numeral test shared by extract and
structure in `caption_labels.py`):

- **Lines interleaved.** The height rule let a tall junk box over the
  hieroglyphs (26 to 35 pt) give its height to body words, so two printed
  lines merged on pages 38 and 44 and body text moved into a note on
  page 27. A Tesseract word now takes a height only from a layer box no
  taller than 1.5 times the page's 90th percentile of layer heights
  (the median failed on pages 11 and 15, where notes outnumber text).
- **Invented text** from kept layer words ("84", "97", "•J4", "US", "w",
  "inn") and two copies of a Tesseract word: a kept word now needs 2
  letters, and 4 with 0.7 of letters when its row holds at most one
  other kept word; the copy test looks along the word's own line. 45
  layer words are kept, all printed.
- **A false reference** ("find" taking the "1" of the layer's "flui1"):
  the letters must now match, not only their count.
- **A word lost without a record** (page 11's "the", matched to one a
  line below): the reach is the word's own line.
- **A right caption changed** (page 38's "MAP VI." to "vi."): the
  layer's numeral is taken only when Tesseract's is not one.
- 13 surviving mutations now pinned; stale wording and counts fixed.

Kadesh with redo now: 40 linked notes (the 2 fewer were false links),
3 headings, 42 pages with footnotes, 59 words with a layer reference or
caption numeral. pytest 3,064 passed in 69 s, still over the minute;
`pytest -m whole_book -k kadesh` 22 passed.

**Still wrong:** page 27's three text lines under the hieroglyphs,
skewed on the scan, are read 9.3 pt tall and become a note; with the
layer on main they were a quotation in the text. Task 5.2 looks at it.
