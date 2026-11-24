# Report: fewer wrong note links, fewer notes joined

For the owner. Started on 24 November 2026, at main a908204. The plan is
`docs/plans/wrong-links.md`.

## Summary

Done on branch `plan/wrong-links`, 24 November 2026, but for task 5.2
(Kadesh rebuilt with the vision model), which waits for LM Studio. The
seven books are rebuilt in `runs/wrong-links/<folder>/`, all through
epubcheck with no error or warning. Every link that changed against the
builds before the plan was checked on the page images: none of the
changed links is wrong; 3 right links were given up, all in Kadesh.

| book (folder) | links | wrong before | wrong after | right links lost |
|---|---|---|---|---|
| Domesday (`domesdaybook00maituoft`) | 1,589 → 1,614 | 10 | 3 | 0 |
| Haskins (`normansineuropea00hask`) | 69 → 69 | 2 | 1 | 0 |
| Gierke (`politicaltheorie00gieruoft`) | 296 → 296 | 1 (page 42) | 0 | 0 |
| Kadesh (`battleofkadeshst00breauoft`), without the model | 45 → 33 | 15 | 1 | 3 |
| Stubbs, Turney, Haynes | unchanged | — | — | — |

Haskins' "wrong before" counts page 56, which work package 3 made wrong
and fixed on the way. Notes that held the next note's text: Domesday
36 → 9, Haskins 1 → 0. Domesday's notes with the right reference
(galley-eval): 1,563 → 1,594.

Wrong links left: Domesday 154 and 498 (a sign read where nothing is
printed, at the place the next reference is expected), Domesday 333 (a
"2" read as 3), Haskins 204 (a "*" with nothing printed, on the page's
only note), Kadesh 54 (the reference to 144 read "I'*").

The right links given up, by the owner's rule of no wrong link: Kadesh
pages 18, 26 and 52.

Left open: Kadesh with the vision model (task 5.2, about 26 minutes of
LM Studio; the earlier build with the model had 105 links, 95 right);
the wrong links above; a link the model places one word off.

## Work package 2: unmarked notes and signs

Done (99848e6 spec, 9682a3b code). In books numbered per page, a
footnote with no marker, or a sign (`*`, `^`, `•`), is linked only
where the page expects it: the page's first note, or the note before it
linked. Domesday's wrong links on page indices 106, 200 and 499 (two)
are gone, each checked on the page image; Domesday links 1,589 → 1,585,
galley-eval's right count unchanged at 1,563; Haskins 68 right,
unchanged. Gierke, Kadesh (without the model), Stubbs, Turney and
Haynes: blocks.json byte-identical.

Still wrong: Domesday 154 and 498 (the sign sits where the order
expects a reference; the real one was read as a word or an amount),
Haskins 204 (the page's only note, two candidates, the earlier wins).

Changed from the plan: the rule is not applied to books numbered
through (Kadesh), where it unlinked 15 of 45 links, three of them right
by the spec's own record; and a sign may link the page's first note,
not only its only note, which keeps 6 right Haskins links.

## Work package 1: the measure

Done (d2e8d3a spec, daf32ac code). `uv run galley-eval compare domesday
haskins`, on copies of the more-note-links builds in
`runs/evaluation/`, writes in each `evaluation/summary.md` the links to
a note other than the transcription's and the notes holding the next
note's text, by page index. A link is right when its note begins like a
note the transcription references within 3 tokens.

Baseline (the builds of 23 November 2026, before this plan):

- Domesday: 13 wrong links, the plan's 10 and 3 the evaluation cannot
  tell from wrong (104, where the transcription keeps only one of two
  printed "3"; 156 twice, a table it orders differently); 36 joined
  notes, the investigation's 24 and 12 it missed.
- Haskins: wrong link 204, joined note 29, as the plan says.

Changed in the plan: the target of work package 3 is restated on 36
joined notes, at most 12 left.

## Work package 3: notes joined on one line, and continuation lines

Done (71ef75f, c793b00, 2763161, 5029320, bcc4299, a91b64e, e3bf3d8).
A footnote is cut where a later marker reads the next number, or, when
the marker is misread ("«", "-", "&", "B"), where a later one reads the
number after it, or at the page's last note after a 20 pt gap, or at a
line under a row of notes. A number starting a line inside a note is a
marker only when it is the next number after a sentence's end. New
excerpt `domesday_joined_notes` (page indices 177, 187, 207, 213, 225,
335, 440, 445, 504, 517).

| book | joined notes | right links | wrong links |
|---|---|---|---|
| Domesday | 36 → 10 | 1,563 → 1,593 | 9 → 6 (3 of them the transcription's quirks) |
| Haskins | 1 → 0 | 68 → 68 | 1 → 1 (204) |

Joined notes left in Domesday: 123, 136, 157, 166, 240, 269, 291, 311,
449, 504. Domesday 440, 445, 517 now linked right; every cut checked on
the page images. Gierke: page 42's reference 2 moved to its right note
(page image), notes 384 → 385. Kadesh without the model: a false note on
page 63 removed, links unchanged; page 21's notes were already separate
in this build, page 27's markers are read as quotes and no rule reaches
them. Stubbs, Turney, Haynes byte-identical.

A cut on Haskins page 56 first made a new wrong link: the OCR lost the
first note's reference, and the second note's sign took the first note.
Fixed by a rule: a sign link to a note started by a guessed cut, or to
the note just before it, is kept only when the other of the two is also
linked. Page 56's sign is now unlinked. (After the review only the line
under a row of notes counts as a guessed cut; the stand-in cuts are
taken as sure, which changes no book.)

The whole-book bound on Domesday's unreferenced notes
(`test_whole_book_domesday_signs_followed_by_punctuation_link_their_notes`)
rose from 286 to 287: work package 2's removal of 4 wrong links took
the count from 284 to 288, unseen because that test is in the slow set;
work package 3 brings it to 287.

The marker's own number, kept when a reference reads it, changes no
link once the cuts exist.

## Review of work packages 1–3

Four reviewers (spec, tests, fidelity, conventions) on a908204..92526e8.
No word lost, doubled or reordered on four whole books; no new wrong
link. What was found and fixed (ca26451, e3c131a, a44a03b, 4be4881):

- A wrong link older than this plan on Domesday page 504: notes 5 and 6
  side by side, 6 read "8", the reference to 6 linked to the joined
  record. A marker one confused digit from the next value now starts a
  note after an 8 pt gap; the link is right on the page image.
- The cut at a line under a row of notes had no check that the line
  before ends as before a note; it has now (it cost no note).
- 13 rules or guards changed a book or guarded one with no test failing
  without them; each now has a test, or was dropped where it changed no
  book: the rule "a marker's own number" (no link changes once the cuts
  exist), a branch of the sure links implied by another, a lower-case
  condition the older lone-letter rule covers.
- galley-eval's texts name its constants; defaults that hid a choice
  (`guessed`, a note's start) are required; one helper for a marker of
  digits; names and docstrings; the spec's figures.

After the fixes: Domesday 1,594 right, 6 wrong (3 of them the
transcription's), 9 joined; Haskins 68, 1, 0.

## Work package 4: Kadesh's wrong structure links

Done (fbc6e6c, b8ae704, 3a0fac9, 6b6bd19), in books numbered through
only, which of the seven is Kadesh alone. Every Kadesh link built
without the vision model was checked against
`tests/fixtures/expected/kadesh_reference/` or the page images: there
were 15 wrong of 45, not the 8 the plan counted (pages 37, 41, 47, 53,
54, 60, 63 besides the plan's).

| Kadesh without the model | links | right | wrong |
|---|---|---|---|
| before | 45 | 30 | 15 |
| after | 33 | 32 | 1 |

The rules: a note loses its marker's value when another note of its
page reads the same number, or when it is out of order with two values
of its page that are in order; a sign scores less against a note whose
marker stood for a number; a reference one more or less than a note's
value is not a misread of it; after the first page with a two-digit
value, a note gets no one-digit value; a sign linked to its page's first
note is unlinked unless the page's second note is linked too.

The owner's rule (no wrong link) decided two trades: the one-digit rule
removed the wrong links on 31, 41, 63 and the right ones on 18 and 26;
the sign at a page's head removed 6 wrong (21, 27, 37, 47, 53, 55) and 1
right (52). A stricter sign rule (a linked number on each side) would
have cost 5 more right links and was not kept.

Left: page 54, where the reference to 144 was read "I'*" and takes note
141. The other six books' blocks.json are byte-identical.

## Review of work package 4 and the first fixes

Four reviewers on 92526e8..2dff022 (the hand merge of the two streams
included; it drops and adds nothing, the books built from it equal each
stream's). No word lost, no new wrong link. Fixed (976ffde, db72cb0):

- The one-digit rule would have cost right links in a book whose notes
  restart at 1 in each chapter, or after one early misread; it now runs
  only when the book's two-digit values rise through it (the longest
  rising run holds at least half of them: Kadesh 45 of 73).
- "A value out of order" decided no link once the one-digit rule ran
  first, and was removed; the spec credits pages 14 and 61 to the
  one-digit rule.
- The confused next-marker cut got the tests that its gap, capital and
  digit conditions lacked (without the gap condition, three links on
  Domesday page 390 move).
- A link from a lone number to a note whose head-of-page sign was
  unlinked rests on the number read; Kadesh has none. Left, with a test.
- Defaults that hid a choice made required; an unused function and four
  copies of a grouping removed.

All seven books' blocks.json byte-identical to before these fixes.
Default pytest: 74.2 s, against 74.8 s on main a908204 measured the
same way; the plan does not slow the tests.
