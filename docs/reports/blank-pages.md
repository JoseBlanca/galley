# Report: pages without a text layer, read by Tesseract

Plan `docs/plans/blank-pages.md`, run on 26 November 2026. Done on
branch `plan/blank-pages`, not merged.

## What exists now

analyze reads every page without a text layer with Tesseract instead of
stopping (`docs/specs/analyze.md`). On the five public-domain whole
books, 68 such pages: 47 blank and left out with `blank_checked_by_ocr`,
9 plates by the plate rule, 8 pictures kept as plates (covers, boards,
a reader's handwriting, a faint relief), 4 read as text (two Internet
Archive notices, two library labels). No page with print was judged
blank on these books. Each book converts from its PDF with only title,
authors and language:

| book | time, 6 threads, M5 Pro | epubcheck | audit warnings |
|---|---|---|---|
| `battleofkadeshst00breauoft` | 8 s | clean | 8 |
| `domesdaybook00maituoft` | 105 s | clean | 3 |
| `earlyplantagenet01stub` | 57 s | clean | 6 |
| `normansineuropea00hask` | 19 s | clean | 4 |
| `politicaltheorie00gieruoft` | 73 s | clean | 6 |

Checks on the branch: pytest 3902 passed in 90 s (81 s before the
plan); 8 threads pass; `-m whole_book` 176 passed in 630 s.

## Open for the owner

1. Picture pages without a layer (covers, boards, labels) stay in the
   book as images, each logged at WARNING; Stubbs' last page, a barcode
   label, ends its text with "0 020 690 469 0". Meanwhile kept
   (analyze.md Open 1).
2. The config's `cover_page` is not audited. Meanwhile so (Open 2).

## Limits

- A page whose only print is one short word or a page number in body
  type can look blank: Tesseract reads nothing and its ink is below the
  picture threshold. A blank page with ink at or above half that
  threshold is logged at WARNING; on the five books, four pages
  (Gierke 5 and 286, Kadesh 75, Haskins 279), all blank by eye.
- Tesseract is now needed for every run, under `ocr = "trust"` too.
- The audit's language is not tested: every excerpt is English.
- The second half of the audit (a sample of pages with a layer scored
  against Tesseract) is not built.

## Review

Four reviewers (spec, tests, fidelity, conventions) on 5aa4517. Fixed
in 85673bf, 73bce60, 657e7cb: the lone-word blank page (warning and a
softer spec claim); text words found on a plate and an empty Tesseract
page now logged; the closing count line counts what pages became; four
untested branches tested; one dropped cli test case restored; a loose
tolerance tightened; the page segmentation mode shared by analyze and
extract in `ocr.py`; names and docstrings. Not taken: removing the
cover guard in `classify_page`, which carries spec §2 rule 4; a test of
the audit's language, which needs a non-English excerpt; the PDF form
writing `book.toml` before the Tesseract check, which is the user's
own config.

## For whoever next revises a skill or writes a plan

The spec writer measured on whole books and looked at every page by
eye, and still the reviewers found the lone-word case by pasting a
word onto a blank page: a made-up adversarial page is a cheap check of
a "never" claim in a spec.
