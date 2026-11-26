# Plan: fewer misread words, with the vision model

The owner chose on 25 November 2026 ("option 1, go on") a plan that
fixes the single words the scan's text layer misread and that reach the
EPUB: three of Haynes' chapter headings with a misread word, Haskins'
"G^ricault", Domesday's "I i, is not". The owner was away when the
breakdown was made and asked the session to go on ("you go on,
especially on improving the pipeline for these and future books"), so
the breakdown below was decided by the session and is reported to the
owner with the results. Dated 25 November 2026. State: done on 26 November 2026.

Spec: `docs/specs/correct.md` (the correct stage). A rule this plan adds
goes into the spec in a commit of its own before the code.

## What was found (25 November 2026)

The correct stage exists and has been run on Kadesh only. It may already
change every word of a text page but note markers, references, heading
labels, epigraph sources, contents page numbers and running heads
(`correct.md` §5, §7), so Haynes' headings are in its scope. A trial on
4 pages (Haskins 19, 22; Domesday 29, 75), each edit judged against the
page image, with the 35B model (`qwen/qwen3.6-35b-a3b`):

- Haskins: 5 edits, 5 right ("Géricault", "Siècle", ...), 16 s a page.
- Domesday: 12 edits, 6 wrong. Five wrong edits are in Latin ("cniht" →
  "cnihl", "obiit" → "obiiit", "quieta" → "quiet a"); one is "I i," →
  "I It,": two of galley's words for one printed word, the stray "I"
  kept. The junk "(lu*fc k"8" (page 75) was left.

The 27B model was right as often on Haskins, wrong 4 times in 10 on
Domesday, and 3 to 5 times slower. Scratch files of the trial:
`tmp/misread-survey/` of the main checkout.

Words that look misread, in the current builds (`runs/reading-fixes2/`),
odd signs inside a word + letters mixed with digits + glued words:
Haskins 70, Stubbs 84, Turney 100, Haynes 198, Gierke 309, Domesday 631.

The model's answers are not kept: every change to the merge rules needs
the model again, about 15 s a page, 1 to 3 hours a book.

## In and out

In: keeping the model's answers in the book folder; whole-book runs on
the six books (Kadesh has one); judging a sample of each book's edits by
the page image; rules for the wrong edits found, among them two of
galley's words read as one printed word, and passages in another
language; a recommendation per book for `correct = true`.

Out: tables; Stubbs' margin notes; the wrong note links left from
wrong-links; turning `correct` on by default (a reader-visible change,
the owner's).

## Must be in place

- LM Studio on `localhost:1234` with `qwen/qwen3.6-35b-a3b` available
  (`curl -s localhost:1234/v1/models`). Only models the session loaded
  are unloaded.
- The whole books in `samples/public_domain/` and the owner's two in
  `samples/` of the main checkout.

## 1. Keep the model's answers

What it gives: a run of correct writes each page's answer from the model
into the book folder, and a second run with the same page image, model
and prompt reads it there instead of calling the model.

Deliverables:
1. The spec part that says where the answers are kept, what makes one
   stale and how a run reuses them, and `docs/architecture.md`'s book
   folder with it. Check: read by the orchestrator.
2. Tests: a second run on an excerpt with a fake server makes no call
   and writes the same `edits/correct.jsonl`; a changed prompt or model
   calls again. Check: `uv run pytest -k answer_store` lists them and
   they pass; it exits 5 on the starting commit.

Tasks:
- [x] 1.1 Spec, then code in `src/galley/correct/`, then the tests.

## 2. Run the books and judge the edits

What it gives: each of the six books run with correct, its answers
kept, and for each a count of right and wrong edits on a sample judged
by eye.

Deliverables:
1. `galley-eval edits <run>`: for a random sample of N edits (seeded),
   an image of the line of each edit, cut from the page at the edit's
   box, beside galley's word and the model's. Check: run on the Kadesh
   run, the images exist and show the words.
2. Whole-book runs, in `runs/misread-words/<folder>/`, Haynes and Turney
   first. Check: `edits/correct.jsonl` and the kept answers exist for
   every text page.
3. 60 edits a book judged right, wrong or unclear, by subagents reading
   the images; the verdicts of the public-domain books committed under
   `tests/fixtures/expected/edits/`, those of the owner's books only as
   counts, in the report. Check: the counts in the report.

Tasks:
- [x] 2.1 The `edits` subcommand of galley-eval.
- [x] 2.2 The runs (orchestrator, one book at a time in LM Studio).
- [x] 2.3 The judging, one subagent a book.

## 3. Rules for the wrong edits

What it gives: fewer wrong edits, measured on the judged samples with
the kept answers and no model.

Deliverables:
1. Each rule in the spec before its code, with the cases from the
   samples that made it: at least two of galley's words read as one
   printed word ("I i" → "It"), and passages not in the book's language
   left alone or held to a stricter likeness. Others as the judging
   finds them.
2. A test per rule, built from a recorded answer of a public-domain
   page, that fails on the starting commit.
3. On the judged samples: wrong edits fewer, right edits kept, each
   counted per book in the report.

Tasks:
- [x] 3.1 Spec of the rules, from the verdicts of 2.3.
- [x] 3.2 Code and tests.

## 4. Rebuild and recommend

Deliverables:
1. Every book rebuilt from the kept answers, its EPUB passing epubcheck
   and the fidelity check. Check: the run logs.
2. The report: per book, edits, right and wrong on the sample, words
   that still look misread; Haynes' three headings named by page; a
   recommendation for `correct = true` per book.

Tasks:
- [x] 4.1 Rebuild and count.
- [x] 4.2 Report.

## At the end

`uv run pytest`, the 8-thread run and `uv run pytest -m whole_book`;
the scan for the owner's books' text over every commit of the branch
before the owner is told.
