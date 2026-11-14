---
name: writing-specs
description: How a stage spec, and the architecture document, are written in galley. Use it when writing or revising docs/architecture.md, docs/glossary.md or a document under docs/specs/, which says what one stage of the pipeline does, the format of the file it reads and the file it writes, its public functions, the cases that matter, how it is verified, and what is left for the owner to decide. The prose follows the writing skill, read first.
---

# Writing specs

A spec says what one stage of galley does and how we will know that it
does it. It is written before the code, and the plan, the tests and the
code are made from it. It is also the contract that lets two sessions
build two stages at once: each one builds against the formats the specs
give, and not against the other's code.

A spec lives in `docs/specs/<stage>.md`: `analyze`, `extract`,
`structure`, `correct`, `markdown`, `epub`. The formats shared by several
stages, the dataclasses of `src/galley/model.py`, are described in
`docs/architecture.md`, and a spec points to them instead of copying them.

## The architecture document

`docs/architecture.md` is written first, before any spec, because every
spec, plan and stage stands on it, and `src/galley/model.py` is written
with it. It is written and reviewed as a spec is, with the same readers,
the first reader and the spec reviewer, and the owner settles it before
the first spec. It defines what the skills refer to as "what the
architecture gives":

- each stage: the files it reads (the PDF, the book config, the file of
  the stage before) and the one file it writes, with its name, and where
  a run of a book writes its files;
- what the markdown stage reads when correct is skipped;
- the dataclasses of each format in `model.py`, their `format_version`,
  and the one pair of read and write functions for each;
- the record of removed text: its fields (page, box, reason) and the enum
  of reasons;
- the fidelity check: its module and function, how a text is split into
  words, and how it reads the Markdown and the EPUB;
- the one PDFium module: its name and what it offers (open, page sizes,
  render at a DPI);
- the other modules of the package root: the config reader, `errors.py`
  and its subclasses of `GalleyError`, the worker-count constant;
- the book config: its TOML keys, their defaults and the dataclass;
- coordinates (PDF points, origin top left), page index from 0 against
  printed page number, and how the DPI travels with a value in pixels;
- the entry point of a stage, `run(...)` or other, the CLI command
  `galley2epub` with its subcommands, and `[project.scripts]` (gilguard
  is already imported first by `src/galley/__init__.py`, decided by the
  owner on 14 November 2026);
- the log of the correct stage, and how the vision model is called;
- the word list that guards hyphen joins;
- the tiers of tests and the pytest markers (already in `pyproject.toml`
  and the `coding` skill; the architecture points to them).

`docs/glossary.md` is started with it: running head, page number
(printed) and page index, line (a line of the PDF, not of the book once
hyphens are joined), block, removed text, reference page.

## The two readers

The owner reads a spec to check that the right thing will be built and to
decide the points that are theirs. The implementer, usually a subagent,
reads it to build the stage without working anything out again. Every
paragraph is for one of the two; what is for neither goes out.

The test for a sentence: would an implementer who has seen the input
files get this wrong without it? Would the owner decide differently
without it? When both answers are no, it goes out. That a running head is
removed is obvious. That a line repeated on facing pages differs in its
page number, `47` against `48`, and must still be recognised as the same
running head, is not, and belongs in the spec.

## Before writing

1. Look at real input. Open the excerpts under `tests/fixtures/pdf/`, the
   whole books under `samples/public_domain/`, and the
   output the previous stage gives today, if it exists. Write down what
   you find that a reader of the format would not expect: a page with no
   text layer, a footnote that continues on the next page, a ligature
   extracted as one character, a hyphen that is part of the word.
2. Read `docs/architecture.md` and `docs/glossary.md`. A term the spec
   needs and the glossary lacks is added there.
3. Read the code worth reusing, in `ocr_lab` or elsewhere, and its
   notes on what failed.
4. Make the sketch the writing skill asks for.
5. Ask the owner, in chat, what would rewrite the spec if answered later:
   the public functions and the formats in a line each, and any open
   point whose other answer would change several parts. An open point
   that moves one value stays in the spec with its "meanwhile". When there
   is nothing to ask, say so in a line and go on.

A claim about what a PDF contains or what a program does comes from
running it on the sample, and says which book and page.

## The parts of a spec

**The opening.** What the stage gives, in a paragraph; the date; what
code exists; the file it reads and the file it writes.

**What it does.** In words first, then the rules: how a running head is
recognised, when two lines are one paragraph. Each threshold is given
with where it comes from, measured on a sample or guessed.

**The public interface.** The function the pipeline calls,
`run(input_path, output_path, config) -> None` or what the architecture
gives, the CLI subcommand, and any other function another stage calls,
each with a sentence before it, in a code block. Nothing private.

**The format it writes**, when it is not a format of
`docs/architecture.md` unchanged: the fields it fills, the ones it leaves
empty, and what each value means. A change to a shared format is a change
to `docs/architecture.md` and `model.py`, and is an open point for the
owner, because other stages read it.

**What it removes, and how it says so.** Any text the stage drops, a
running head, a page number, a blank page, is recorded in its output with
the reason, as the architecture says. A stage that drops text without a
record is wrong, whatever it drops.

**The cases.** Those where the result is not what the rules would make a
reader expect, and those the tests must hold: a page with two columns, a
chapter that starts on a page with no running head, a footnote that runs
on, a page of the index. Only what changes the result.

**How it runs in parallel**, when it does: over pages, what one page needs
from the others (a running head is found by looking at many pages, so it
is a pass over the whole book before the per-page work), and the rule
that the output does not depend on the number of threads.

**How it is verified.** The reference pages: pages of the committed
excerpts (a case no excerpt has gets a new excerpt in
`scripts/fetch_samples.py`, from a public-domain book),
named by book and page, whose expected output the owner has checked by
eye, and what is compared and how (exactly, for the words and their
order; by kind, for the blocks). The fidelity check: which words of the
input must be in the output, and which can be missing with a record. Each
check names the public function it is made at.

**Open points.** What the owner decides, numbered, each as the writing
skill asks for a decision, with what the implementer does meanwhile.

**Not in this spec.** What a reader could expect here and is elsewhere, in
a few lines.

A part with nothing to say is a line or is left out.

## Decided, inherited and open

Every statement is one of three kinds, and the reader can tell which.
Decided: stated, with a reason when there was a real choice. Inherited:
taken from ocr_lab or from Pandoc's behaviour, with where. Open: marked
in the text as "(**Open 2**, below)" and listed once at the end.

Few open points, each worth the owner's time: what changes what a reader
of the EPUB sees, or a format other stages read. A name or a private
layout is decided by the writer.

Once code exists, the spec changes first: a new case, a changed decision,
an answered open point goes into the spec in a commit of its own, before
the commit of the code.

## Before handing it over

1. The `first-reader` subagent, once as the owner and once as the
   implementer. For the implementer: what comes out for a page with no
   text layer, which words may be missing from the output, what the first
   test asserts. For the owner: what is asked of me.
2. Every **Open** in the text is in the list, and nothing in the list is
   decided elsewhere in the text.
3. The `spec-reviewer` subagent, with the path of the spec and the sample
   pages it talks about. Evaluate each finding on its evidence; take what
   makes the spec more right or easier to build from. Tell the owner which
   findings were not taken, a line each.
