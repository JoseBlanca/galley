# Plan: the correct stage on a second book, and Kadesh's pages without links

The owner read Kadesh (`battleofkadeshst00breauoft`) with the correct
stage on 21 November 2026, found it "very good", and said to go on.
The stage is off for books whose OCR is good until it is measured on a
second book (`docs/specs/correct.md` §16). Dated 21 November 2026.
State: approved; under way.

## 1. The correct stage on Domesday

Domesday (`domesdaybook00maituoft`) has good OCR, many footnotes and
small type. Read six of its pages from the images (body, footnotes, a
page with Latin, a table page) word by word and commit the reference
under `tests/fixtures/expected/domesday_reference/`. Run the correct
stage (35B, links, second reading) on those pages and score, as the
notes-vision measurement did: wrong words per 100 in body and notes
before and after, fluent wrong words, words lost, links made and wrong,
doubtful edits and how many are wrong, time per page. Then recommend
whether the stage should be on for a book like Domesday, and write the
result into `docs/specs/correct.md` §16.

- [ ] 1.1 The reference.
- [ ] 1.2 The measurement and the recommendation.

## 2. Kadesh pages without links

On 13 Kadesh pages (13, 14, 26, 28, 29, 31, 36, 40, 46, 53, 61, 62, 63)
the model's reference numbers did not run in order, so the stage gave
no link. Find, from the model's answers on those pages, why (missed
references, misread numbers, notes merged by galley), and whether a
narrower check links some of them without a wrong link; every link
checked on the images against `tests/fixtures/expected/kadesh_reference/`
where it covers the page, otherwise on the image. Build only with no
wrong link.

- [ ] 2.1 The cause and, if found, the rule.

## 3. The end

- [ ] 3.1 Review; all checks; the EPUBs touched rebuilt and through
  epubcheck.
