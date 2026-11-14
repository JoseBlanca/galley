---
name: coding
description: How code is written in galley, a Python 3.15 free-threaded package run with uv. Use it before writing or changing any code or test. It covers the order of the work, the functional style (pure functions, frozen values), the file formats between stages, keeping every word of the book, threads and PDFium, errors, types and names, dependencies and external programs, the tests, and the checks to run before the work is called done.
---

# Coding

galley is a pipeline of stages, `analyze → extract → structure →
correct → markdown → epub`, each a subpackage of `src/galley/`. The
stages talk only through files whose formats are the dataclasses of
`src/galley/model.py`, described in `docs/architecture.md`. What a
stage does is in its spec, `docs/specs/<stage>.md`. The goals, in order:
no word of the book lost or invented; a readable EPUB; fast enough to run
on a book while making coffee. When two pull apart, the earlier one wins.

Many rules below are enforced by the ruff and ty configuration in
`pyproject.toml`. A rule a lint enforces is given here with its reason and
the rule code; the prose is for what no tool catches.

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
   empty tuple or `None`, so that the test fails on its assertion and not
   on an import error. Run it and see it fail. A change that cannot have
   such a test, a rename or a move, says so in the commit message.
2. The code, as small as the task asks.
3. The checks at the end of this file, all of them, with their real output.
4. One commit, with the message the `writing` skill describes.

## Functional style

galley's data is small, a few thousand lines of a book, so the code is
written as pure functions over frozen values, and copying a value is never
a cost worth avoiding.

- A function's result depends only on its arguments. It does not change
  its arguments, read or write module state, or do I/O. A stage's work is
  a chain of such functions, `page lines → lines without running heads →
  blocks`, each tested with literal inputs and outputs and no mocks.
- Side effects live at the edges: the stage's `run` function reads its
  input files, calls the pure functions, writes its output file and logs;
  the CLI parses arguments and calls `run`. PDFium, subprocesses, HTTP and
  the thread pool are called from the edges, or from a function that does
  nothing else, whose result is a frozen value the pure functions use.
- Every value that leaves a function is frozen: frozen dataclasses, tuples,
  `frozendict`, `frozenset`, strings, numbers, enums. A changed value is a
  new one, made with `dataclasses.replace` or the constructor. Inside a
  function, a local list built and returned as `tuple(...)` is fine:
  what matters is that nothing that escapes can be mutated.
- Classes hold data, functions hold behaviour. No class with mutable state,
  no methods that change `self`, no inheritance except for exceptions and
  enums. A `Protocol` when a function takes interchangeable things.
- A generator is consumed where it is created; it is not stored in a value
  or passed to another thread.
- Pure functions are what makes the threads safe: a worker calls a pure
  function on one page and returns a frozen value, and nothing it touches
  is shared.

## The formats between stages

- A stage reads the PDF, the book config and the file of the stage before
  it, as `docs/architecture.md` lists for each stage, and writes one file.
  It imports nothing from another stage. What stages share is in
  `model.py`, and the helpers every stage needs (the config reader, the
  PDFium thread, the fidelity check) are modules of the package root that
  the architecture names.
- The formats are frozen dataclasses with `slots=True`, and `kw_only=True`
  when they have more than three fields. Sequences in a format are
  `tuple[X, ...]` and mappings `frozendict[K, V]` (new in 3.15), never
  `list` or `dict`, because a `list` field makes a frozen instance mutable.
  A "not given" default is a `sentinel` (new in 3.15) when `None` is a
  valid value.
- Each format has a `format_version` field and one pair of functions in
  `model.py` that write and read it. Reading rebuilds the enums and tuples
  that JSON turned into strings and lists. JSON is written with
  `ensure_ascii=False`, a fixed key order and a fixed indent, so that the
  file is byte-identical whatever the number of workers. No stage writes
  JSON by hand.
- A field or a format is changed in `model.py` and `docs/architecture.md`
  together, and only by the task the plan gives for it, because other
  stages read it. A stage that needs a field nobody fills says so to the
  orchestrator.
- Coordinates are PDF points with the origin at the top left of the page,
  pages are indexed from 0. A value in pixels of a render carries the DPI
  beside it.
- The book config is TOML, read with `tomllib` in one place into a frozen
  dataclass. A stage receives that dataclass, not a dict. An unknown key
  in the config is an error, not ignored.

## No word lost, none invented

This is the first goal and the easiest to break without noticing.

- A stage never drops text without a record. A running head, a page
  number, a blank page or a region the config excludes is kept in the
  stage's output in the list of removed text the architecture gives, with
  its page, its box and the reason, a member of an enum. A `continue` in a
  loop over words or lines is a place to check for this.
- Hyphens are joined only when the joined word is in the word list the
  architecture names or appears elsewhere in the book unhyphenated, as
  `rejoin_hyphens_guarded` in ocr_lab does. A blind join invents words:
  ocr_lab's scorer made `tomatoda` that way.
- Text that a model wrote, a vision model reading a line or a correction,
  never enters the book except through the `correct` stage and its rules,
  and every change it makes is in its log with the old and new word.
- The fidelity check compares the words of a stage's input and output,
  minus the recorded removals. Every stage's tests run it on their
  fixtures.

## Threads and PDFium

The project runs on free-threaded Python so that per-page work runs in
parallel. Measured on 14 November 2026, pdfplumber's `extract_text` on 200
pages of the Turney sample, one document per thread, on an M5 Pro with 6
performance cores: 4.5 s with 1 thread, 1.2 s with 6, and no gain beyond
6. With the GIL on, 4 threads took 4.8 s, no faster than one.

- Parallel work goes through `concurrent.futures.ThreadPoolExecutor`, over
  pages. The number of workers is a parameter whose default is one named
  constant, `min(6, os.process_cpu_count())` with the measurement above in
  its comment, never the executor's own default (22 on that machine). The
  output is in page order and byte-identical with 1 worker and with 8.
  InterpreterPoolExecutor cannot load pdfplumber or Pillow, and a process
  pool was no faster (1.0 s against 1.2 s on the same pages).
- Workers share no mutable state. A worker takes a page and returns its
  result; the merging happens in the calling thread. `functools.lru_cache`
  may be shared when computing a value twice is harmless; anything else
  shared and mutable takes a `threading.Lock`. No iterator or generator is
  shared between threads. A check-then-act on a shared dict (`if k not in
  d: d[k] = ...`) is a race even when each operation alone is safe.
- pdfplumber's text extraction is pdfminer, pure Python, and runs in
  workers, but each worker thread opens its own `pdfplumber.open(path)`
  (through `threading.local` or the executor's `initializer`). A `PDF` or
  `Page` object is never shared between threads: sharing one raised
  `PdfminerException: pop from empty list` in 6 of 6 runs with 4 and 8
  workers.
- PDFium is not thread-safe, not even across two documents (pypdfium2
  documentation). Every call into pypdfium2 goes through the one PDFium
  module the architecture names, which runs them in one thread. That
  module renders with pypdfium2 directly, never with pdfplumber's
  `to_image` (which uses pypdfium2 and reopens the whole PDF on each call),
  and closes every page, bitmap and document explicitly, with `with` or
  `.close()`, so that no finalizer runs PDFium from a worker's garbage
  collection. Images go to workers as fully loaded Pillow images.
- Tesseract and Pandoc run as subprocesses, and the vision model through
  HTTP; workers can wait on them in parallel.
- A C extension that does not declare free-threading support turns the GIL
  back on when imported, with only a `RuntimeWarning`. The first line of
  `src/galley/__init__.py` imports gilguard, a runtime dependency with no
  dependencies of its own, so a run of `galley2epub` stops at such an
  import too; that import stays first. Every pytest run also
  loads gilguard (`-p gilguard` in `pyproject.toml`), which turns that
  into `gilguard.GILEnabledError` at the import that caused it, naming the
  module, its package and the line of our code. The error derives from
  `BaseException`, so an `except ImportError` or `except Exception` around
  an optional import cannot swallow it. A warning turned into an error by
  `filterwarnings` is a `RuntimeWarning`, which such an `except` does
  swallow: on 14 November 2026 a test whose import sat in `try/except
  Exception` passed without gilguard and failed with it.
  `tests/test_free_threading.py` also asserts `sys._is_gil_enabled()` is
  False after importing every module. Imports that happen late (Pillow
  plugins on first open) are caught only on the code paths the tests run.
  Tests never run with `PYTHON_GIL=0` or `-X gil=0`, which hides the
  problem and risks crashes.

## Errors

Errors never pass silently. This is the owner's rule, and it has no
exceptions below the top of the program.

- A `try` is written only for a particular exception that is expected at
  that line, named in the `except`, and handled in a way that keeps the
  failure visible: raised again as a `GalleyError` with context, or turned
  into a record in the output (a page that cannot be read becomes a
  removed-text record with its reason), never into a default value, an
  empty result, a skip or a `pass`.
- When no particular exception is in mind, there is no `try`. The error
  propagates.
- The one place that may catch broadly is the outermost function of the
  CLI, and only to log or report the error before raising it again. It
  does not exit quietly and does not change the exception.
- `contextlib.suppress` is an `except: pass` and follows the same rule.
- Ruff enforces part of this: no bare `except` (E722), no `except
  Exception` or `BaseException` unless re-raised (BLE001), no
  `try/except/pass` or `continue` (S110, S112, SIM105). What it cannot see,
  an `except ValueError: return None`, is for the writer and the reviewer.
- One exception class for the package, `GalleyError`, in `errors.py`,
  with a subclass for each kind of failure a user would handle
  differently. The message says which file, which page, which value, and
  is built before the `raise` (EM, TRY003).
- An exception raised while handling another uses `raise ... from err`
  (B904), so the original cause is kept.
- External programs are found with `shutil.which` at start-up; a missing
  `tesseract` or `pandoc` is an error that names it and how to install it,
  raised before any work starts.

## Types, names and defaults

- Type hints on every function (ANN), checked by ty with every rule an
  error. A finite set of values is a `StrEnum`, never a bare string; a
  `match` on it ends with `case _: assert_never(value)`, so that a member
  left out is a type error. `Self` for the return of a classmethod
  constructor, `@override` on a method that overrides one.
- No `from __future__ import annotations`: on 3.14 and later, annotations
  are evaluated lazily by default (PEP 649/749). Ruff bans the import.
- A name says what the value is: `line_height_pt`, `running_head_lines`,
  never `n`, `data`, `tmp`. The names of the domain are those of
  `docs/glossary.md`, and the same thing has the same name in every stage.
- A value that changes the output, a threshold or a margin, is a named
  module constant (PLR2004) with a comment that says where it comes from:
  "0.6, measured on Turney pages 20-60" or "guessed, not measured".
- No `bool` parameter that switches behaviour (FBT); an enum with two named
  members.
- Paths are `pathlib.Path` (PTH), files are opened with
  `encoding="utf-8"`. No `print` outside the CLI module (T20); progress
  and diagnostics go through `logging.getLogger(__name__)`.
- Private by default (`_name`). What another module calls is in the
  stage's `__init__.py` and in its spec, with a docstring as the `writing`
  skill describes.

## Dependencies and external programs

- A new dependency installs on 3.15t as a wheel: `uv pip install
  --only-binary :all: <pkg>` in a scratch venv made with `uv venv --python
  3.15t`, and once added, `uv run python -m gilguard` reports no
  package that turns the GIL back on at import. The
  commit that adds it says what it gives and why it is not a few lines of
  our own. The JSON formats use the standard library; msgspec installs on
  3.15t and is the fallback if parsing is ever measured as slow.
- Development tools are pinned to exact versions in `pyproject.toml`
  (ruff, ty, pytest and its plugins), because a new ruff or ty release
  changes what the checks report. Raising a pin is a commit of its own.
- Code from ocr_lab is copied and adapted, not imported, and the commit
  says from which file. Tesseract is called by our own subprocess wrapper,
  adapted from ocr_lab's `tesseract_words`, not through pytesseract.
- Subprocesses run with a list of arguments, `check=True` (PLW1510) and a
  timeout.

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
- Every reader gets malformed input as cases of its own: truncated JSON, a
  wrong `format_version`, a missing field, a config with an unknown key, a
  page range past the end of the book. Every field of the config takes, in
  some test, a value other than its default.
- Parallel code is tested with 1 worker and with several, on more pages
  than workers, and the outputs compared byte for byte. The checks also
  run the tests themselves in 8 threads at once with pytest-run-parallel,
  which catches state shared between calls; a test that calls PDFium is
  marked `thread_unsafe` and runs once.
- Tests that need the sample PDFs, Tesseract or Pandoc are marked
  `samples`, `tesseract` or `pandoc` (registered in `pyproject.toml`) and
  skip with the reason when it is missing. The `samples_dir` fixture of
  `tests/conftest.py` finds the samples through `GALLEY_SAMPLES` or in
  `samples/` of the main checkout, so tests in a worktree find them too.
  A skip is reported as a skip, never as a pass.
- A test's name says the behaviour and the outcome:
  `test_running_head_with_changing_page_number_is_removed`.

## Before the work is called done

```
uv lock --check
uv run --locked ruff format --check
uv run --locked ruff check
uv run --locked ty check
uv run --locked pytest
uv run --locked pytest --parallel-threads=8 -m "not samples"
```

Report what each printed when it failed, and the counts of passed and
skipped when it passed: "5 skipped" may be the whole of the new work.
pytest exits with 5 when it collected no test, which is "not run", not a
pass. A check that could not be run is reported as not run. Speed is not
claimed without a measurement: book, pages, workers, machine, before and
after.

## When this skill is wrong

It was written on 14 November 2026, before any code, and its tooling
rules were checked that day against ruff 0.17.5, ty 0.0.104 and pytest
9.2.0. When a rule proves wrong or a check is missing, correct it here
with what showed it.
