# Plan: three faults left after the note-links plan

The owner said to go on on 21 November 2026, after merging the
note-links plan. Its report left three faults. Dated 21 November 2026.
State: approved; under way.

## 1. A quotation taken for a heading (Kadesh)

On Kadesh (`battleofkadeshst00breauoft`) page 39 a quoted inscription
("The stand which his majesty made…") is made a level-2 heading, so the
unlinked notes of pages 8 to 38 gather before it. Find why the heading
rule takes it (structure §14), fix with the narrowest rule, spec first,
a test that fails first; count the headings that change on the seven
books and look at each.

- [x] 1.1

## 2. Wrong note links made by galley (Kadesh pages 9, 10)

Galley's own linking (structure §11, not the vision model) links
"Lenormant" to note 4 instead of 5 and "Chabas" to note 5 instead of 6
on page 9 (the "‘" after "Salvolini" was not read as note 4's mark), and
"(see above)" to note 11 instead of 14 on page 10. Find the cause, fix
with the narrowest rule, spec first, tests; count links that change on
the seven books and check a sample on the page images (the references
read by eye in `tests/fixtures/expected/kadesh_reference/` cover pages
8, 9, 11, 13, 15, 25, 26, 27, 29, 40, 47, 53).

- [x] 2.1

## 3. The quick tests back to about a minute

They take 75 to 105 s. Find where the time goes (`--durations=30`, the
excerpt fixture, the correct stage's excerpt test, the Tesseract
excerpts) and cut it without dropping a check.

- [x] 3.1

## 3b. A misread mark left before a vision-model link

Where the scan's OCR read a note's raised number as a sign, a link the
correct stage adds leaves the sign in the text: "soldiers;™", "map®",
"iter™", "whatever.™" on Kadesh (run `runs/note-links/battleofkadeshst00breauoft-correct2/`).
The link should take the sign's place, as galley's own references do.
Spec first (correct.md §9b), a test that fails first.

- [x] 3b.1

## 4. The end

- [ ] 4.1 Review; all checks; `pytest -m whole_book`; the seven EPUBs in
  `runs/small-fixes/` through epubcheck; the evaluation against
  `runs/note-links-final/`.
