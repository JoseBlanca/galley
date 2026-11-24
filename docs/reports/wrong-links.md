# Report: fewer wrong note links, fewer notes joined

For the owner. Started on 24 November 2026, at main a908204. The plan is
`docs/plans/wrong-links.md`.

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
linked. Page 56's sign is now unlinked.

The whole-book bound on Domesday's unreferenced notes
(`test_whole_book_domesday_signs_followed_by_punctuation_link_their_notes`)
rose from 286 to 287: work package 2's removal of 4 wrong links took
the count from 284 to 288, unseen because that test is in the slow set;
work package 3 brings it to 287.

The marker's own number, kept when a reference reads it, changes no
link once the cuts exist.
