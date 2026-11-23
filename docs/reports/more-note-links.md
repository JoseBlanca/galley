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

Task 2.2 (fa61ab4 spec, 23c719c code): when k notes lie unlinked
between linked neighbours N−1 and N+k, the gap's words that read as
those notes are linked only when there are exactly k of them, in order;
links made this way never serve as neighbours. New links, Turney /
Haynes: a lone number 7 / 6, glued digits that are part of N 23 / 1,
a sign 8 / 0, Haynes' note 57 by its place. Unlinked: Turney 65 → 27
of 613, Haynes 13 → 5 of 632; Gierke gains 11 links. Every new link
was checked on the page images: none wrong; two lone numbers (Turney
p83, p123) sit one word before the printed reference, because the text
layer puts the number before the last word.

**Turney misses the plan's bar, 27 against 25.** What is left needs a
letter linked ("n", "N"), which the fidelity check forbids for a
reference, digit misreads outside the confused pairs, or gaps with
fewer readable words than missing notes. The whole_book bars are 30
and 7.

**Copyright.** Two fragments of Haynes (a word glued to a reference
number and the word after its dash) had gone into the spec, a
docstring and a test of 2.1. They were replaced with made-up words
and the stream branch's history rewritten before any merge
(`git filter-branch`), so no commit holds them.

## Work package 3: endnotes run into the note before

Done (4294a46 spec, 0fb14b3 code). A line inside an endnote, not its
first, starts a new note when its first word is the next number in the
section's marker form ("N." or "N-" in Haynes and Gierke, a bare "N" in
Turney), the line before ends a note (a full stop, or a number and a
hyphen: Turney's OCR reads a closing "p. 487." as "487-"), and the
section's next marker is not that number. 63 of the 67 run-on endnotes
found by the investigation are cut: Haynes 632 → 691 endnotes, Turney
613 → 618; 61 and 3 new links, none wrong. Unlinked: Haynes 5 → 3,
Turney 27 → 29 (two new notes whose references the body lacks or
garbles). Gierke 299 → 311 endnotes, 10 new links; the 12 new starts
and 5 links checked on the images. The four other public-domain books
are byte-identical. Not caught: Haynes 11, Turney 41 and 42, whose
number does not start a line.
