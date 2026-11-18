# Report: stray text in the body

The work report of `docs/plans/stray-text.md`, written as the work goes,
for the owner. Started on 18 November 2026.

## Before the first task

The plan was written on 18 November 2026 from two investigations of the
eight books' runs at main a0a1675; the owner said to write it and go on
without waiting. Pandoc, Tesseract and epubcheck are installed; the
public-domain books and the owner's two PDFs are in `samples/`.

Two of the defects the owner reported on 17 November are already fixed
on main: the Haskins running head left in a paragraph (page 23) and the
Haskins footnote of page 28. The plan only checks them.

The investigations' notes and scripts are in `tmp/investigation/` of the
plan's worktree (not committed: they quote the owner's books).

## Work package 1: the specs, the formats and the excerpts

Done in three commits: be06218 (specs), 5141c9f (formats), b54be14
(excerpts). The checks pass: ruff, ty, and pytest with 2,810 passed and
24 expected failures in 80 s (8 threads: the same counts in 128 s).

- **Specs.** The inkless page is a new section 2b of `docs/specs/plates.md`,
  where the 36 dpi render is specified; architecture §8, §9 and §17,
  the glossary, layout steps 2b, 3, 4 and §9, and structure §3, §9 and
  §11 are amended. The first reader and the spec reviewer read them.
  Not taken: requests to define terms layout defines elsewhere, and a
  recount of Haskins 278 at 0.88 for 0.92, which leaves the margin as it
  is.
- **Formats.** pages.json is version 4, with the page kind `inkless`;
  removals gain the reason `inkless_page`. words.json is unchanged.
- **Excerpts.** `haskins_endpapers`, `domesday_notes`,
  `gierke_notes_heads`, `stubbs_cut_in`, with 26 expected files read
  from the page images, and 16 tests marked as expected failures until
  their work package lands.
- **Changed from the plan:** six thresholds and pages, listed in the plan
  under "Changed by work package 1". Each was measured on the eight
  books before it was changed.
- **For the owner:** the quick tests take 80 s, from 70 s; task 5.3 is
  to bring them back. Haskins 277 holds a printed conservator's label
  without text-layer words, so removing the page's words loses no print.
