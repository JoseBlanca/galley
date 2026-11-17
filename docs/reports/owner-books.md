# Work report: owner's books

The work of the plan `docs/plans/owner-books.md`, written as it goes, for
the owner. Started on 17 November 2026 on branch `plan/owner-books`.

## Before the first task

The owner approved the scope in chat on 17 November 2026 and asked that
the specs and the plan be written and carried out without waiting for
their review, since they were away. The specs' open points (structure
§27) were settled by the orchestrator: the epigraph's source and the
note group heading are text fields of their block; group headings stay
out of the table of contents; the markdown step writes the source's
dash as text (a Kindle's support for CSS generated text is untested);
the heading rule's costs on Mariéjol are accepted, Stubbs' publisher's
lists are excluded in its config, and Domesday's 4 false headings are
looked at in task 1.6.

Two surveys ground the specs; their notes are outside the repository
because they quote the owner's books.

**The baseline**, `uv run galley-eval run` on `main` at 9715a93 (3 min
41 s), copied to `runs/owner-books-baseline/` of the main checkout. It
equals Review 3's scores of clean-text: Stubbs' margin notes 291 as
margin notes (error rate 0.244), Domesday's 579 (0.138), Stubbs' index
.984 / .963, Domesday's .995 / .998, body error rates .023 / .055 /
.075 / .310 (Haskins, Stubbs, Domesday, Mariéjol), Domesday's notes
whose reference is right 1,278.

## Task 1.1: the four excerpts

b6c75e7: haskins_heads_notes (13 pages), stubbs_heads (18),
gierke_intro_heads (13) and domesday_rereads (11), with the expected
output of their 36 case pages in `tests/fixtures/expected/owner_books_wp1/`
(the removals, page numbers, headings and note-band starts WP1's rules
must give; each with the printed text read from the 300-dpi render by
the assistant). Pages were added beyond the spec's case pages so that
each excerpt's measures equal its whole book's (Stubbs' line pitch was
7.68 pt against 12.87 without them). The default run went from 46.4 s
to 56.1 s (2,127 passed), 21.4 s of it the excerpts' setup.

Left to work package 1: Gierke pages 72 and 78, whose damaged heads are
0.74 and 0.70 alike, under the spec's 0.75, so they stay in the text
under the rules as written; Stubbs 186 and Gierke 73 record a wrong
page number ("5" for 165, "xviii" for lxviii).

## Task 2.1: the format

418c726: blocks.json version 4 in `model.py` (the epigraph kind, a
block's `source`, a note's `group`, the reasons `source_dash`,
`punctuation_attached` and `case_split`), and the fidelity check's rules
for them at both boundaries. Changed beyond the task's files, with the
orchestrator's leave: the epigraph kind in markdown's two `match`
statements (a plain div until task 6.1) and in galley-eval's two kinds,
whose tests failed and which would have crashed on a real epigraph.
`source` and `group` default to empty, so no other stream's code had
to change. Default run 60.4 s, measured while other streams ran pytest
on the same machine.

## Task 5.1: spaced signs and case splits (stream `words`)

12c38a4, 76d3db2, 6b33a5d, f99da27, merged into the plan's branch. The
pure functions `attach_spaced_sign`, `split_at_case` and their passes
over a block, not yet wired into structure (task 5.2). Counts on the
six books' clean-text lines (signs attached / case splits): Haskins
90 / 2, Stubbs 1,022 / 10, Domesday 2,115 / 3, Gierke 888 / 0, Kadesh
98 / 0; Mariéjol 1,150 no-break spaces and 12 splits.

**Changed from the spec (76d3db2).** As first written, the case split
took 48 Mariéjol words, at least 30 of them misreadings cut in two
("poUtique" for "politique"), and Domesday's "jiEthelbert": Tesseract's
word lists hold "po" and "ji". Now the left part must also be one of
the book's common inner words, and no split is made before a capital U
or H (a misread "li"). Mariéjol's 6 remaining wrong splits are an
accepted cost (the owner's decision on that scan); Domesday's "forSon"
and "forSan" are to be checked on the page in WP 5's review.
