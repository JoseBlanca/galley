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
