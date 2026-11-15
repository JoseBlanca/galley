# Report: regions and paragraphs

The work report of `docs/plans/regions-and-paragraphs.md`, written as
the work goes, for the owner. Started 15 November 2026. State: under
way.

## Before the first task

The plan's branch, `plan/regions-and-paragraphs`, was made from
`spec/structure` (commit 2f50468), not from `main`, because the specs
and the plan it is built from are on that branch and the owner has not
ordered it merged. Merging the plan's branch into `main` brings them in.

Checked on 15 November 2026: `which pandoc tesseract combine_tessdata
dawg2wordlist epubcheck` printed five paths; `tesseract --list-langs`
lists `eng` and `fra`; the six whole books and the four Gutenberg HTML
files are in `samples/public_domain/`; `uv run galley-eval --help`
works; the baseline runs are in `runs/evaluation/` of the main checkout;
`uv run --locked pytest` gave 781 passed, 8 deselected.

## 1. Three new excerpts

Done as planned, commit f8f3c50. `stubbs_51_56-64` (465 KB),
`domesday_74-83` (653 KB) and `mariejol_210-219` (745 KB) are committed,
ten pages each, every page with a text layer; `uv run pytest
tests/test_excerpts.py -q` gives 7 passed. `galley2epub run` on each
wrote an EPUB that epubcheck passes with no error or warning (galley as
it was before this plan, one block per page).

Change to the plan: work package 5 may change `tests/conftest.py`,
where the excerpts' book configs are (`EXCERPT_CONFIGS`); the new
excerpts have none yet, so the end-to-end tests do not run them.

The work package is reviewed together with work package 4, which runs in
the same stream next: its change is a list of page indices in
`scripts/fetch_samples.py`, with no code a review of its own would test.
