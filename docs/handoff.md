# Handoff: where galley stands and how the work is run

Written on 14 November 2026 at the end of the session that set the project
up and carried out the walking-skeleton plan, and updated on 15 November
2026 after the evaluation plan, for the session that takes over. It says what exists, what is being decided, and how the owner wants
the work run, including the practical lessons that no skill records yet.
Read it after CLAUDE.md; replace it when it stops being true.

## What exists

- `main` at b6dcaa3 (local; pushed only to bcec31e,
  https://github.com/JoseBlanca/galley, public). The walking skeleton is
  merged: the `galley2epub` command runs
  six stages (analyze, extract, layout, structure, markdown, epub; correct
  is not built), each in its simplest form, on a book folder holding a
  `book.toml`. 461 tests pass in about 14.5 s (18.5 s with 8 threads).
- Both committed excerpts and both whole public-domain books (Kadesh, 76
  pages; Gierke, 290 pages) become EPUBs that pass epubcheck with 0 errors
  and 0 warnings; Gierke whole takes 7.4 s with 6 workers. The EPUBs are in
  `runs/walking-skeleton/` (ignored by git). They read badly on purpose:
  one paragraph per page, running heads, page numbers and footnotes in the
  text.
- Documents: `docs/architecture.md` (approved by the owner; sections are
  cited by number from the spec, so a new section is inserted as 7b, not
  renumbered), `docs/glossary.md`, `docs/specs/walking-skeleton.md`,
  `docs/plans/walking-skeleton.md` (done), `docs/reports/walking-skeleton.md`
  (the work report: what every review found and fixed, costs, open items).
- Skills in `.claude/skills/`: writing, writing-specs, writing-plans,
  following-plans, coding, reviewing-code; subagents in `.claude/agents/`:
  code-reviewer, first-reader, spec-reviewer.
- The evaluation tool, merged on 15 November 2026 (`docs/specs/evaluation.md`,
  `docs/plans/evaluation.md`, `docs/reports/evaluation.md`): `uv run
  galley-eval run` runs galley on four public-domain books
  (`evaluation/books.toml`) and compares each stage's output with the
  Project Gutenberg edition made from the same scan, giving per book a
  scorecard, the differences with their page and stage, and a table of
  pages for choosing a detector of bad OCR. The baseline of the walking
  skeleton is in the report and in `runs/evaluation/` (ignored by git).
  galley's word list, `wordlist.py`, exists. 781 tests in about 16 s.

## What is under way

The structure stage is next (owner, 15 November 2026), as the baseline
suggests: running heads and page numbers (1,243–1,841 extra words per
book), hyphens left split (985–3,600), paragraphs (about 1 in 10 of
galley's breaks is real), notes and margin notes (none found). Layout
probably comes with it, since margin notes and footnote columns need
regions. Its spec is being written in `.claude/worktrees/spec-structure`,
branch `spec/structure`. A plan is measured by `galley-eval run` before
and after; its report quotes both.

## What comes after

The stage specs that replace the skeleton's simplest rules, each a spec,
then a plan, as the skills say. What is already known for them:

- analyze: the OCR audit of architecture §7b (pages without a text layer
  read by Tesseract and filled or recorded blank; a sample of layer pages
  scored against Tesseract by word-list share). Kadesh page index 69 has
  about five printed lines no text layer holds.
- extract: OCR with Tesseract (adapt ocr_lab's wrapper, not pytesseract);
  what to do with characters XML forbids (markdown refuses them now) and
  with pdfminer's `errors="ignore"` decoding in `pdfminer/cmapdb.py`, which
  can drop a broken character before galley sees it.
- layout: columns, margins and footnote columns (Kadesh's two footnote
  columns are read across the row now).
- structure: running heads, page numbers (two sequences in Kadesh),
  signature marks, paragraphs across pages, guarded hyphen joins (the
  fidelity check verifies every join by its rule), notes and their
  references, margin headings (a block kind; rendered as a small bold line
  before their paragraph, owner's decision).
- markdown: edits and `galley2epub edits-from` (architecture §10).
- epub: style sheet, cover. correct and index stages later.

## How the owner wants the work run

The owner's rules are in CLAUDE.md, the skills and the memory; the ones
that shape the session most:

- The session is the orchestrator and does not write code: subagents
  write code, review and fix. Two or three parallel streams at most, each
  in its own worktree. The orchestrator writes plans, reports, skills and,
  with the owner's approval, the architecture.
- Decisions that change a file format or what the EPUB shows go to the
  owner, with options and a recommendation; the rest are decided and
  recorded.
- Nothing is merged into `main` or pushed without the owner's order.
- Never post issues, pull requests or comments to repositories the owner
  does not own (a pdfminer.six bug is recorded in the report instead).

## Practical lessons of the first plan (not yet in a skill)

- Work from the main checkout and manage every worktree by its path:
  after `EnterWorktree`, a session may not create other worktrees.
- Subagents may be refused git commands outside their own worktree; one
  then commits on a branch of its own worktree and the orchestrator merges
  it. A subagent's edit to `docs/architecture.md` was refused by the
  permission check: such edits go to the owner, then the orchestrator
  makes them.
- `git branch -d` refuses a stream branch merged into the plan's branch
  but not into `main`: check `git branch --merged plan/<plan>`, then `-D`.
  Reviewer worktrees made with `isolation: "worktree"` are locked:
  `git worktree unlock` before removing a clean one.
- Resuming the agent that wrote a piece of work (`SendMessage` to its id)
  keeps its context and costs less than a fresh one for fixes.
- Every review found real defects, most of them tests that could not fail;
  the tests reviewer's mutation pass (break the code, run the tests) is
  what finds them. A work package costs about three times its coding in
  tokens with its review and fixes.
- Timings taken while another agent's stress loop runs are useless; time
  the suite on a quiet machine.
- A library's module-level table is shared state under free threading:
  pdfminer.six's keyword table raced (`PdfminerException: /b'trailer'`,
  about 1 run in 100), fixed by `text_layer.open_pdf` opening under a lock.
- (Evaluation plan.) Reviewers mutating code must clear `__pycache__` or
  set `PYTHONDONTWRITEBYTECODE=1`: a stale bytecode cache hid mutations
  twice. Reviewer worktrees made with `isolation: "worktree"` start from
  `main`; the prompt has them check out the commit under review.
- (Evaluation plan.) For a tool that reads or aligns text, the most
  useful review was the fidelity category adapted to "is any word lost,
  invented or counted twice", done by an independent parse diffed word
  by word. Specs of pairing rules must say how near and how alike two
  things must be: every review round found a rule without that limit.
