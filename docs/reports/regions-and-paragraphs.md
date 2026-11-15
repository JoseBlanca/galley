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
