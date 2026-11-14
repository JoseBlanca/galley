---
name: coding
description: How code is written in galley, a Python 3.15 free-threaded package run with uv. Use it before writing or changing any code or test. It covers the order of the work, the file formats between stages, keeping every word of the book, threads and PDFium, errors, types and names, dependencies and external programs, the tests, and the checks to run before the work is called done.
---

# Coding

galley is a pipeline of stages, `analyze → extract → structure →
correct → markdown → epub`, each a subpackage of `src/galley/`. The
stages talk only through files whose formats are the dataclasses of
`src/galley/model.py`, described in `docs/architecture.md`. What a
stage does is in its spec, `docs/specs/<stage>.md`. The goals, in order:
no word of the book lost or invented; a readable EPUB; fast enough to run
on a book while making coffee. When two pull apart, the earlier one wins.

## Before the code

Code is written from a spec, usually from a task of a plan. Read the part
of the spec, the parts of `docs/architecture.md` it stands on, and the
sample pages it names.

When the spec can be read in two ways that give different output, run
both readings on the sample page where they differ before choosing. When
the spec does not say what happens in a case, the choice is not made in
silence: a choice that changes what a reader of the EPUB sees or a shared
format goes to the owner; a smaller one is written into the spec in a
commit of its own before the code.

## The order of the work

1. The test first. It asserts what the spec gives and fails before the
   change. The new function gets a body that returns a wrong value, an
   empty list or `None`, so that the test fails on its assertion and not
   on an import error. Run it and see it fail. A change that cannot have
   such a test, a rename or a move, says so in the commit message.
2. The code, as small as the task asks.
3. The checks at the end of this file, all of them, with their real output.
4. One commit, with the message the `writing` skill describes.

## The formats between stages

- A stage reads its input file and writes its output file, and imports
  nothing from another stage. What two stages share is in `model.py`, and
  the helpers that every stage needs (reading the book config, the one
  PDFium thread) are in modules of the package root named in the
  architecture.
- The formats are frozen dataclasses with `slots=True`, written as JSON
  with a `format_version` field, through the one pair of functions per
  format that `model.py` gives. No stage writes JSON of its own by hand.
- A field or a format is changed in `model.py` and `docs/architecture.md`
  together, and only by the task that the plan gives for it, because the
  other stages read it. A stage that needs a field nobody fills says so to
  the orchestrator.
- Coordinates are PDF points with the origin at the top left of the page,
  pages are indexed from 0, and the architecture says so once. A value in
  pixels of a render carries the DPI beside it.
- The book config is TOML, read with `tomllib` in one place into a frozen
  dataclass. A stage receives that dataclass, not a dict.

## No word lost, none invented

This is the first goal and the easiest to break without noticing.

- A stage never drops text without a record. A running head, a page
  number, a blank page or a region the config excludes is kept in the
  stage's output in the list of removed text the architecture gives, with
  its page, its box and the reason, a member of an enum. A `continue` in a
  loop over words or lines is a place to check for this.
- Hyphens are joined only when the joined word is in the dictionary or
  appears elsewhere in the book, as `rejoin_hyphens_guarded` in ocr_lab
  does. A blind join invents words: ocr_lab's scorer made `tomatoda` that
  way.
- Text that a model wrote, a vision model reading a line or a correction,
  never enters the book except through the `correct` stage and its rules,
  and every change it makes is in its log with the old and new word.
- The fidelity check, a function the architecture names, compares the
  words of a stage's input and output, minus the recorded removals. Every
  stage's tests run it on their fixtures.

## Threads and PDFium

The project runs on free-threaded Python so that per-page work runs in
parallel in threads.

- Parallel work goes through `concurrent.futures.ThreadPoolExecutor`, over
  pages, with the number of workers a parameter whose default is in one
  named constant. The output is in page order and is the same, byte for
  byte, with 1 worker and with 8.
- Workers share no mutable state. A worker takes a page and returns its
  result; the merging happens in the calling thread. A cache shared
  between threads has a lock, or is not there.
- PDFium is not thread-safe, not even across two documents. Every call
  into pypdfium2, and into pdfplumber's `to_image`, which uses it, goes
  through the one module the architecture gives, which runs them in one
  thread. pdfplumber's text extraction is pdfminer, pure Python, and can
  run in workers.
- Tesseract and Pandoc run as subprocesses, and the vision model through
  HTTP; workers can wait on them in parallel.
- A dependency with a C extension that does not declare free-threading
  support turns the GIL back on at import, with only a warning. A test
  imports the whole package and asserts that `sys._is_gil_enabled()` is
  False.

## Errors

- One exception class for the package, `GalleyError`, in `errors.py`,
  with a subclass for each kind of failure that a user would handle
  differently. The message says which file, which page, which value.
- A missing external program, `tesseract` or `pandoc`, is an error that
  names it and how to install it, raised before any work starts.
- No bare `except`, no `except Exception` that goes on. An error is not
  turned into a default value, and a page is not skipped without a record.

## Types, names and defaults

- Type hints on every function. A finite set of values is a `StrEnum`,
  never a bare string; a `match` on it names every member.
- A name says what the value is: `line_height_pt`, `running_head_lines`,
  never `n`, `data`, `tmp`. The names of the domain are those of
  `docs/glossary.md`, and the same thing has the same name in every stage.
- A value that changes the output, a threshold or a margin, is a named
  module constant with a comment that says where it comes from: "0.6,
  measured on Turney pages 20-60" or "guessed, not measured".
- No `bool` parameter that switches behaviour; an enum with two named
  members.
- Private by default (`_name`). What another module calls is in the
  stage's `__init__.py` and in its spec, with a docstring as the `writing`
  skill describes.

## Dependencies and external programs

- A new dependency installs on 3.15t as a wheel: `uv pip install
  --only-binary :all: <pkg>` in a scratch venv first. The commit that adds
  it says what it gives and why it is not a few lines of our own.
- Code from ocr_lab is copied and adapted, not imported, and the commit
  says from which file.
- Subprocesses run with a list of arguments, `check=True`, and a timeout.

## Tests

- Fixtures are small files in the formats of `model.py`, written by hand
  or cut from a sample, under `tests/fixtures/<stage>/`. A stage's tests
  need only its own fixtures, never the output of another stage's code.
- The expected values are literals: the words, the kinds of the blocks,
  the Markdown. They come from the spec or from a reference page the
  owner checked by eye, never from running the code under test.
- A test has to be able to fail. Check that the fixture reaches the
  condition: a running head test whose pages all have the same running
  head cannot tell repetition from position. When in doubt, break the code
  and see the test fail.
- Parallel code is tested with 1 worker and with several, on more pages
  than workers, and the outputs compared.
- Tests that need the sample PDFs, Tesseract or Pandoc are marked
  (`samples`, `tesseract`, `pandoc`) and skip with the reason when it is
  missing. A skip is reported as a skip, never as a pass.
- The name of a test says the behaviour and the outcome:
  `running_head_with_changing_page_number_is_removed`.

## Before the work is called done

```
uv run ruff format --check
uv run ruff check
uv run pytest
```

Report what each printed when it failed, and the counts of passed and
skipped when it passed. A check that could not be run is reported as not
run. Speed is not claimed without a measurement: book, pages, workers,
before and after.

## When this skill is wrong

It was written on 14 November 2026, before any code. When a rule proves
wrong or a check is missing, correct it here with what showed it.
