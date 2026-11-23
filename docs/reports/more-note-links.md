# Report: more note references found and linked

For the owner. Started on 23 November 2026, at main f69b847. The plan is
`docs/plans/more-note-links.md`.

## Summary

Done on branch `plan/more-note-links`, 23 November 2026, but for the
parts of work package 5 that need LM Studio. No reviewer found a wrong
link or a lost word; every new link checked on the page images was
right but one on Domesday page 106, which was wrong before too.

| book (folder) | measure | before | after |
|---|---|---|---|
| Turney (`turney`) | endnotes with no link | 83 of 613 | 27 of 618 |
| Haynes (`haynes`) | endnotes with no link | 50 of 632 | 3 of 691 |
| Gierke (`politicaltheorie00gieruoft`) | endnotes with a link | 208 of 299 | 230 of 311 |
| Domesday (`domesdaybook00maituoft`) | notes whose reference is right (galley-eval) | 1,432 of 1,729 | 1,563 |
| Haskins (`normansineuropea00hask`) | the same | 66 of 72 | 68 |
| Kadesh (`battleofkadeshst00breauoft`) | footnotes linked without the vision model | 43 | 45 |

Domesday's "before" is with the corrected evaluation (work package 1);
with the old one it was 1,307. Domesday falls short of the plan's +150
(+131). Turney's endnotes rise to 618 because 5 notes run into the note
before are cut off; Haynes' by 59 for the same reason.

The owner decided on 23 November 2026 that a "V" glued to a word may be
a footnote link's text where the numbering expects a reference (6
Domesday links); see the last section.

The EPUBs of the seven books are in `runs/more-note-links/<folder>/`,
all through epubcheck with no error or warning.

Left open: the Kadesh work that needs the vision model (the page-order
fallback for garbled first words, the narrower order check, the rebuild
with the model); recording the model's answers on 18 pages takes about
15 minutes, the rebuild about 35.

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

## Review of work packages 1–3

Four reviewers (spec, tests, fidelity, conventions) at 7500c30. None
found a wrong link or a lost word in the outputs. All findings held and
are fixed (77c019b to 69d36d9):

- Examples in the spec, code, tests, plan and report were copied from
  the owner's books (mostly reference forms such as a year and a glued
  number, a few with a word); all replaced with made-up forms of the
  same shape, none of which occurs in either book. The branch history
  is rewritten before the merge so that no commit holds them.
- The gap rule read digits after a range's dash or a currency sign
  ("1914-18", "£5"); it no longer does. Gierke loses one right link
  (note 322, read "elaborated3-2.").
- A gap word can be taken by one run only, so that out-of-order links
  could never link one word to two notes.
- About 15 checks had no test that failed without them; each has one
  now. One filter could not be reached and was removed.
- galley-eval: a reference now maps after the last token before it
  aligned to the body outside a margin note. Domesday 1,410 → 1,432;
  the 22 more are right on the reference text, 6 checked on the images.

Counts after the fixes: Turney 29 unlinked of 618 endnotes, Haynes 3 of
691; Gierke 311 endnotes, 228 with a link (208 before the plan).

## Work package 4: Domesday's footnotes

Tasks 4.1 and 4.2 done on a stream branch (08a6e99, 47b32d9, 7ced95a,
0602c96, 93b160a; merged with the review fixes in 18e550e). A footnote
starts at a one-character marker followed by a capital after a short
line, at a number after a 20 pt gap, or at the next note's marker after
an 8 pt gap; a sign starts a note only when the number after confirms
it. A note's value follows a scored numbering of the page's markers,
not only its place; a note the numbering leaves out takes no reference.
New footnote references: a lone backslash before a capital, a star
glued after a number, the last digits glued after a year or amount
(footnotes only), a lone 1–2 digit number after a word ending in a
letter when no other word of the gap ends in the note's digits, and 5
for 8 among the confused digits.

**Domesday misses the bar**: notes whose reference is right 1,432 →
1,557 of 1,729 (+125; the plan asked +150). Haskins 66 → 68 of 72.
Links more than 3 words from their reference: 114 → 49. Wrong links
found on the way (a "*" note taking the next note's reference, table
rows and "9 furlongs" cut into notes, a left-out note taking a stray
sign on Gierke p31, lone numbers matching "(Poem, 1. 17)" and "thus:
8." on Kadesh) were removed by narrowing the rules. One stays: Domesday
page 106, "justice*" links to a signature mark that layout puts in the
notes band; before, that mark took note 5's reference, also wrongly.

Not done: a trailing "V" for a printed reference (about 11 notes, the
likeliest way to the bar) — the fidelity check refuses a letter as a
reference outside round brackets (architecture §13), so it is the
owner's decision. Gierke 228 → 230 linked endnotes (5 for 8, both right
on the images); Turney 29 → 27 unlinked.

Review of work package 4 (two reviewers: spec and fidelity; tests and
conventions). No lost word, no new wrong link; about 50 changed links
checked on the images. Fixed (e800015 to b3def51): five narrowing rules
that no test caught now each have a test, and the whole-book bounds are
tight (Domesday unreferenced ≤ 295, now 290; Turney ≤ 28, Haynes ≤ 4
unlinked, now 27 and 3); the spec no longer names a letter marker the
code never reads; stale docstrings, the source of three constants, two
defaults made required; and a reference linked by the lone-number rule
now sits against its word ("child[1]." instead of "child [1].").
Counts unchanged.

## Work package 5: Kadesh's footnotes

Task 5.1, structure half (a9527c4 spec, 7786d52 code): on a band's
first line, a 1–3 digit marker after a 20 pt gap and before a capital
starts a note; a page whose first line is a row of notes gives its first
note the signs glued to its first word as marker. Kadesh footnotes 183
→ 187 (notes 72, 83, 176, 178 cut from the note before), 4 of the 13
column joins; linked without the vision model 43 → 45 (one from work
package 4, one here, both right on the images). The other books are
byte-identical. Not fixed: p62 (169 read "16°"), the lost or non-digit
markers of p21, 25–28, 55, the splits on p13 and p63, note 87 in the
body on p36. On p32 the second line of the row, holding the ends of
notes 82 and 83, all goes to 83. The tests are unit tests modelled on
pages 29, 32 and 66 and one excerpt test on `kadesh_redo` page 9: the
other Kadesh excerpts are cut from the text layer, which reads these
markers otherwise.

Waiting for LM Studio: the page-order fallback of the correct stage
(rest of 5.1) and the narrower order check (5.2) need the model's
answers on 18 Kadesh pages recorded once as fixtures, about 15 minutes;
the correct stage keeps no copy of its answers.

## The trailing "V" (the owner's decision of 23 November 2026)

3831117, fad574e, 7e6c9fc. A "V" glued to the end of a word whose part
before ends in two lower-case letters, followed only by punctuation,
becomes a footnote reference where the page's numbering expects one
between neighbours; a neighbour is a linked note or the page's start or
end (at least one of the two a note), because the owner's own example,
"adquesieritV" on page 53, refers to the page's last note. The fidelity
check accepts exactly this case. Six new Domesday links (pages 53, 89,
289, 326, 356, 537), all right on the images; 1,557 → 1,563. "oxenV"
(page 167) stays unlinked: it lies before a run of two missing notes.
The other six books are byte-identical. A review found the check's
exception would also take a "V" from inside a word, and a test that
could not fail for its stated reason; both fixed.

## For whoever next revises a skill or writes a plan

- Agents took short examples from the owner's books into the spec, code
  and tests twice, although the brief forbade it; the conventions
  reviewer found the second time. The coding skill's rule on samples
  should say that an example is made up even when it is one word or a
  number form, and that each example is checked against the books'
  blocks.json. The branch history was rewritten before the merge.
- Targets given as counts in a plan were estimates from an
  investigation; two were missed by a few notes (Turney 27 against 25,
  Domesday +131 against +150) once each rule was narrowed to make no
  wrong link.
