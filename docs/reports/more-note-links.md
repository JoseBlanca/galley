# Report: more note references found and linked

For the owner. Started on 23 November 2026, at main f69b847. The plan is
`docs/plans/more-note-links.md`.

## Work package 1: the evaluation's note count

Done (a538264, 8bea196). galley-eval maps a note reference with no
aligned body token after it in its block to the gap after the block's
last aligned token. On the `runs/small-fixes/` outputs, Domesday's notes
whose reference is right rise from 1,307 to 1,410 (+103, the plan said
about 107–126); none right before is wrong now; Haskins stays at 66,
Stubbs has no notes. 102 of the 107 cases past a margin note now score
right; of the 19 past a table, quote or "...", 18 stay wrong because
the alignment drifts inside the block, which is the tables' work, out
of this plan. Two galley-eval tests, each failing without its half of
the change. Results in `runs/more-note-links-eval1/`.

From now on the plan's Domesday counts start from 1,410.

## Work package 2: endnote references in the owner's books

Task 2.1 (73e03c2 spec, cd84541 code, on the stream branch): endnotes
take a number after a year or a closing bracket with sentence
punctuation between, a glued number with no citation-abbreviation
exclusion, and either before a dash and a word. Unlinked endnotes: Turney
83 → 65 of 613, Haynes 50 → 13 of 632; all links of both books checked
for number and chapter, none wrong. Footnote matching is unchanged; the
five public-domain books give byte-identical `blocks.json`. 23 unit
tests on made-up words, 4 whole_book tests that only count.
