# Plan: pages without a text layer, read by Tesseract

Today analyze stops on any page that has no text layer and that the
config does not exclude (`docs/specs/walking-skeleton.md` §6), so most
whole books need `exclude_pages` before they convert, and the PDF form
of `galley2epub run` (architecture §14) fails on them. The whole Gierke
book (`politicaltheorie00gieruoft`) stopped on 13 pages. This plan
builds the first half of the OCR audit that architecture §7b already
decides: every page without a text layer is read with Tesseract in
analyze; a page where Tesseract finds no text is `blank`, recorded with
`blank_checked_by_ocr`, and left out with a record; a page where it
finds text gets `text_source` `ocr`, and extract reads it with
Tesseract as it already does under `ocr = "redo"`
(`docs/specs/extract.md` §9).

The owner chose this on 26 November 2026 ("go with option 1"), from a
description of the option in chat, which stands as the approval of
this breakdown. Dated 26 November 2026. State: under way.

## In and out

In: analyze's spec of this audit (a new `docs/specs/analyze.md`, which
takes over analyze from walking-skeleton §6); the stray-mark threshold,
measured on the pages without a layer of the public-domain books; the
code; a new excerpt; the check for Tesseract before analyze; the
README's limits.

Out: the second half of the audit, the sample of pages with a layer
scored against Tesseract (architecture §7b), and `text_layer_score`;
they stay as the skeleton left them, and the spec says so. Pages with a
poor layer (that is `ocr = "redo"`).

## Must be in place

- `which tesseract`, with English, French and German data
  (`tesseract --list-langs`).
- The whole public-domain books in `samples/public_domain/` of the
  main checkout.

## 1. The spec

What it gives: `docs/specs/analyze.md`, which says how a page without a
layer is read, the threshold that tells a blank page from one with
print (stray marks, a library stamp, show-through from the next page),
measured on every page without a layer of the public-domain whole books
and named by book and page, what is recorded for a blank page, what
`cli.py` checks before analyze, and the reference pages of a new
excerpt.

Deliverables:
1. The spec, read by `first-reader` and `spec-reviewer`, findings
   handled. Check: read by the orchestrator.
2. A new excerpt in `scripts/fetch_samples.py` with at least one blank
   page without a layer and one page with print and no layer (Kadesh
   page index 69 is one). Check: the PDF exists under
   `tests/fixtures/pdf/` and `pdfplumber` finds no words on those pages.

Tasks:
- [ ] 1.1 Measure, write the spec and the excerpt.

## 2. The code

What it gives: `galley2epub run <pdf> --title … --author … --language
…` builds the whole Gierke and Kadesh books with no `exclude_pages`.

Deliverables:
1. Tests of each rule of the spec on the new excerpt, failing on the
   starting commit. Check: `uv run pytest -k blank` lists them and they
   pass.
2. Every public-domain whole book run through the PDF form, with only
   title, authors and language, to an EPUB that passes epubcheck, or a
   named reason why not. Check: the run logs, in the report.
3. `uv run pytest -m whole_book` passes, the whole-book configs
   unchanged.

Tasks:
- [ ] 2.1 Code and tests in `src/galley/analyze/` and `cli.py`.
- [ ] 2.2 Review (reviewing-code), fixes.
- [ ] 2.3 Whole-book runs and the README's limits.

## At the end

The checks of the `coding` skill, the 8-thread run, `-m whole_book`,
and the scan for the owner's books' text before any push.
