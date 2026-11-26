# Report: fewer misread words, with the vision model

Work report of the plan `docs/plans/misread-words.md`, started on
25 November 2026 on branch `plan/misread-words`. State: done on
26 November 2026.

**What you should read first.** The plan is done on branch
`plan/misread-words`, not merged. A scanned PDF carries a text layer,
the words an OCR program read from the page images when the book was
scanned; galley's text comes from it, misread words included. The
correct stage, galley's optional step that has a local vision model
(Qwen 3.6 35B in LM Studio) read each page image and propose fixes where
it reads a word otherwise, was run on all seven books, and 60 to 80 of
each book's proposed fixes, drawn at random, were checked by eye against
the page images. Before this plan, 22 to 39 of 60 fixes were right on
five of the books; on the owner's two books half or more were wrong,
most of them in the index and the bibliography. New rules now refuse
most of the wrong fixes; of the right ones they refuse none on six books
and 1 of 22 on Turney. Of the fixes that still reach the EPUB, an
estimated 8 in 10 or more are right on every book but Stubbs (6 in 10);
the estimate rests on 26 to 78 checked fixes a book. Haynes' three
misread chapter headings, Haskins' "Géricault" and Domesday's "It is
not" now read right.

What exists now: the model's answers are kept in each book folder, so a
book is rebuilt with new rules, or after a fix to another stage, in
about a minute and with no model; a tool cuts an image of each fix for
checking by eye and counts what a rule keeps and drops; and the EPUBs of
all seven books are in `runs/misread-words-final/<folder>/`.

Asked of the owner:
1. The merge order. Some commits of this branch held words of the
   owner's books (since replaced in the files); the merge should be a
   squash, one commit on `main`, so that none of them enters `main`'s
   history.
2. Whether to turn `correct = true` on for each book (recommendation in
   work package 4: on for all but Stubbs). It is off by default.
3. A look at the two EPUBs of the owner's books:
   `runs/misread-words-final/haynes/book.epub` and
   `runs/misread-words-final/turney/book.epub`.

Left open: galley's fidelity check, which proves that no word of the
book is lost between stages, takes every fix as allowed and so cannot see
a word a fix loses (a check is proposed in the spec, not built); two names in Domesday
still split ("Wulf sige", "haul a"); Stubbs' margin notes; LM Studio
crashed three times on Domesday and the run had to be restarted by hand.

## Work package 1: keep the model's answers

Done. The correct stage writes each answer of the model to
`answers/<kind>-<page>.json` in the book folder, keyed by the SHA-256 of
the request's bytes (model, prompt, page image, parameters), and reuses
it on a later run; LM Studio is asked for only when a page has to be
read (`docs/specs/correct.md` §4b). Check: `uv run pytest -k
answer_store`, 10 tests, then more after the review; all pass.

Review, four categories:
- Fidelity: no way found for a kept answer to put an edit on wrong
  words; after a note was moved in blocks.json only that page's band was
  asked again and the edits equalled a fresh run's.
- Spec: a run whose answers were all kept still demanded LM Studio,
  which defeats the purpose. Fixed: the server is checked before the
  first request actually sent.
- Tests: the second reading's answers were never run by a test, nor the
  atomic write, nor that the bytes sent are the bytes hashed. Fixed, with
  tests that fail when the code is broken; the atomic-write test found
  that a failed move left its temporary file, now removed.
- Conventions: model text with a lone surrogate failed without naming
  the page; fixed. Two small style points fixed.
- Not taken: a warning when a kept answer's text was changed by hand;
  the spec allows hand changes and the edit is still recorded.

Task 2.1, `galley-eval edits` and `edits-score`
(`docs/specs/evaluation.md` §9b), was built alongside. One 8-thread run
of the whole suite gave one error whose details were lost; 30 repeated
runs of the tool's tests did not reproduce it. It ran while the model
loaded the machine; it is noted here in case it comes back.

The default test run took 153 s on the plan branch, measured while the
vision model was reading a book on the same machine; it was 75 to 86 s
unloaded. Not yet measured unloaded after the merge.

## Work package 2: run the books and judge the edits

The correct stage, with `qwen/qwen3.6-35b-a3b` in LM Studio on the
owner's machine, read the whole of each book on 25 and 26 November 2026
(`runs/misread-words/<folder>/`, the answers kept in `answers/`):

| book | text pages read | minutes | edits | answers cut short |
|---|---|---|---|---|
| haynes | 419 | 61 | 929 | 2 |
| turney | 292 | 39 | 467 | 0 |
| normansineuropea00hask | 261 | 33 | 377 | 0 |
| earlyplantagenet01stub | 304 | 39 | 506 | 1 |
| politicaltheorie00gieruoft | 272 | 44 | 2,002 | 1 |
| domesdaybook00maituoft | 539 | about 135, with 3 restarts | 2,627 | 1 |

LM Studio crashed three times on Domesday ("The model has crashed", on
pages 191, 352 and 506, each while reading a page's note references); each
time the run was started again and took the answers already kept, so no
page was read twice. Kadesh was read again without its second model
(`correct_second_model`), because loading that model unloaded the first
("Model unloaded"); its earlier run kept no answers.

Each book's edits were sampled (seed 0) with `galley-eval edits`, and a
subagent judged each sampled edit against its image. Kadesh's edits come
from the run of the plan second-book (`runs/reading-fixes2/`).

| book | judged | right | wrong | unclear |
|---|---|---|---|---|
| battleofkadeshst00breauoft | 60 | 51 | 8 | 1 |
| haynes | 60 | 32 | 28 | 0 |
| turney | 60 | 22 | 36 | 2 |
| normansineuropea00hask | 60 | 39 | 21 | 0 |
| earlyplantagenet01stub | 60 | 22 | 38 | 0 |
| politicaltheorie00gieruoft | 80 | 57 | 21 | 2 |
| domesdaybook00maituoft | 80 | 62 | 17 | 1 |

The model helps most where the scan's text layer is poor (Kadesh, Gierke)
and least on the owner's modern books, whose text layer is good: on
those, half or more of its edits were wrong before the rules of work
package 3. The verdicts of the public-domain books are committed under
`tests/fixtures/expected/edits/`; those of the owner's books stay in
their run folders and appear here only as counts.

## Work package 3: rules for the wrong edits

Every rule was written into `docs/specs/correct.md` before its code and
measured by rerunning the stage from the kept answers, with no model,
and `galley-eval edits-compare` against the judged samples. Rules
adopted, with the wrong edits they were made for:

- in an index entry, and in a contents entry, only close edits that
  keep galley's digits (the model pairs words of different entries);
- no replacement that repeats a neighbouring word or glues a note
  reference to a word (page ranges doubled, a year with its note number);
- no replacement by a piece of galley's word two or more characters
  shorter (a word galley joined across a line cut back to its half);
- two of galley's tokens that are one printed word are replaced together
  ("I i," for "It,"), within one block and span, each token once, never
  two one-letter words, and never into a word joined at a line end that
  is in neither the word list nor the rest of the book;
- no inserted run without a letter, or made only of a margin note's
  words;
- no replacement by a long word printed on a nearby line.

Measured and not adopted (spec §16): a stricter likeness everywhere, no
digit changes, no diacritic changes, two spelling rules; each refused
more right edits than wrong ones. A Latin rule waits for Domesday.

On the judged samples, after the first round of rules (right edits kept
/ wrong edits dropped, edits in the book before → after; the final
numbers are in work package 4):

| book | right kept | wrong dropped | edits |
|---|---|---|---|
| haynes | 32 of 32 | 24 of 28 | 929 → 594 |
| turney | 21 of 22 | 31 of 36 | 467 → 273 |
| normansineuropea00hask | 39 of 39 | 14 of 21 | 377 → 340 |
| earlyplantagenet01stub | 22 of 22 | 22 of 38 | 506 → 429 |
| politicaltheorie00gieruoft | 57 of 57 | 9 of 21 | 2,002 → 1,808 |

Kadesh was not rerun (its run kept no answers); checked edit by edit,
the rules keep its 51 right edits and drop 3 of its 9 wrong ones.

Review, four categories, of 528c81a..4033bdc:
- Fidelity found three ways the two-tokens-into-one edit could change
  text: two printed words glued (Stubbs page 167, from the model's join
  at a line end), a merge across two blocks deleting words (shown on a
  made-up page), two merges sharing a token. All fixed with tests.
- Spec: three wrong statements in the spec; fixed.
- Tests: about 15 changes to the rules passed every test; edge cases
  added. Four tests of the kept answers took 31 s together; now 9 s.
- Conventions: an example in the spec quoted an edit from the owner's
  book word for word, and three earlier commits of this branch held
  words of the owner's books. The spec now has a made-up example; the
  commits are to be squashed before the branch is merged.

Second round, after a second fidelity review of the fixes (d452808): the
step that splits one of galley's words into two of the model's lost or
invented characters (Domesday tables "9 0 9" → "0 9" on 7 rows, "1800" →
two numbers of other rows, "337 b." lost its "b", Stubbs "adventurous"
cut to "adventu-", pieces "ever" and "riage" printed twice), merged two
digits of different rows ("0 8 0" → "0 18"), split names ("Brungar" →
"Brun gar") and inserted a word twice. Each was fixed with a rule and a
test, except two names Domesday holds once ("Wulfsige", "haula"), still
split; they are recorded in the spec as known misses. A split now never
loses part of galley's word or a digit, never splits a word the book
holds twice, and never prints a half that is held elsewhere on the page.

markdown's fidelity check did not catch any of these losses: it counts
an edit as an allowed change, so an edit that drops a word passes. The
spec (§15) now says so and proposes a per-edit count of words lost or
doubled; it is not built.

## Work package 4: rebuild and recommend

Every book was rebuilt from its kept answers with the final code
(eff46c0), with `correct_server` pointed at a closed port so that no
model could be asked; each log says "0 asked". Folders:
`runs/misread-words-final/<folder>/`.

| book | edits | right kept | wrong dropped | right among the edits left | words that look misread, before → after | epubcheck |
|---|---|---|---|---|---|---|
| haynes | 585 | 32 of 32 | 24 of 28 | 32 of 36 | 198 → 161 | 0 errors, 0 warnings |
| turney | 272 | 21 of 22 | 31 of 36 | 21 of 26 | 100 → 78 | 0, 0 |
| normansineuropea00hask | 340 | 39 of 39 | 14 of 21 | 39 of 46 | 70 → 20 | 0, 0 |
| earlyplantagenet01stub | 413 | 22 of 22 | 23 of 38 | 22 of 37 | 84 → 60 | 0, 0 |
| politicaltheorie00gieruoft | 1,801 | 57 of 57 | 9 of 21 | 57 of 69 | 312 → 168 | 0, 0 |
| domesdaybook00maituoft | 2,606 | 62 of 62 | 1 of 17 | 62 of 78 | 631 → 289 | 0, 0 |
| battleofkadeshst00breauoft | 1,079 | 51 of 51 | 3 of 8 | 51 of 56 | 49 → 49 | 0, 0 |

"Right kept" and "wrong dropped" are counted on each book's judged
sample (60 or 80 edits, seed 0). "Right among the edits left" is the
sample's right edits over its right and wrong edits that the rules keep:
an estimate, from 36 to 78 edits a book, of how often an edit that
reaches the EPUB is right. Domesday's sample was drawn after most rules
were in, so its wrong edits are those the rules already let through,
and its "1 of 17 dropped" says only that the last rules took one more.
"Words that look misread" counts words of book.md with an odd sign
inside (^ < > | £ € ¬ { }), letters mixed with digits, or a lower-case
run glued to a capital; before is `runs/reading-fixes2/`, built without
the model, except Kadesh, which already had the model's fixes there; so
Kadesh's count compares the old rules with the new and does not move.

Haynes' three chapter headings with a misread word (pages 22, 105,
200) now read right. Haskins' "G^ricault" reads "Géricault", Domesday's
"I i, is not" reads "It is not".

Kadesh's hand edits (`edits/owner.jsonl`, made after checking against
the page images) were rewritten where the new edits moved their text:
2 rewritten, 3 dropped because the model's wrong edits they undid are no
longer made. One footnote on Kadesh's page 21 lost the model's fixes
under the new rules and keeps a few garbled words.

Recommendation, per book, for `correct = true` (left off by default):

- Kadesh, Gierke, Domesday, Haskins: on. Their text layer is poor and
  about 8 in 10 of the edits left are right.
- Haynes and Turney (the owner's books): on. 32 of 36 and 21 of 26 of
  the edits left are right, and Haynes' headings need it. The cost is
  a wrong word that reads as a real word in about 1 edit in 8 (Haynes)
  to 1 in 5 (Turney); the index and bibliography, where most wrong edits
  were, are now guarded.
- Stubbs: off until its margin notes are cut from the paragraphs. 22 of
  37 edits left are right; most wrong ones take a word from a margin
  note mixed into the text.

## Checks at the end

On eff46c0, 26 November 2026, the owner's machine, unloaded:
`uv lock --check` resolved; ruff format and check, ty: pass;
`uv run pytest`: 3,797 passed, 6 xfailed in 80 s (75 to 86 s before
this plan); with 8 threads: the same in 142 s; `uv run pytest -m
whole_book`: 171 passed in 553 s.

## For whoever next revises a skill or writes a plan

- Judging a sample of a stage's output against the page images, one
  subagent a book, took 2 to 5 minutes a book and found the pattern of
  every rule of this plan. A plan that changes what reaches the reader
  should start with it.
- Keeping the model's answers made every rule measurable on seven whole
  books in about a minute; without it each change would have needed 7
  hours of the model. A stage that calls a slow program should keep its
  answers from the start.
- Four reviews found text lost by edits that the fidelity check let
  through. The fidelity category of a review should always rerun a
  whole book and look at the pages, not only at the tests.
- Subagents copied words of the owner's books into tests and the spec
  twice in this plan, although told not to. A scan of every commit of
  the branch against the owner's books, before the merge, is what
  caught it.
