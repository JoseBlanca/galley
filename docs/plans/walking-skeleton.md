# Plan: the walking skeleton

This plan builds the walking skeleton of `docs/specs/walking-skeleton.md`:
the shared modules and every stage of galley but correct, each in its
simplest form, run end to end by `galley2epub run` on the two committed
excerpts, so that each excerpt gives an EPUB and the fidelity check (the
test that no word is lost or invented between a stage's input and output)
passes at the layout, structure and markdown boundaries. It builds on
`docs/architecture.md` and `docs/glossary.md`. Dated 14 November 2026.
State: under way (approved by the owner on 14 November 2026).

The four work packages are the breakdown the owner approved on 14
November 2026, and the spec's sections 3 to 9 follow them. Every task is
made from a section of the spec; this plan says only the order, the
pieces, the files each piece may change and how each piece is checked.
"Spec §6" below is section 6 of `docs/specs/walking-skeleton.md`;
"architecture §8" is section 8 of `docs/architecture.md`.

## In and out

In: `errors.py`, `model.py`, `config.py`, `book_folder.py`, `pdfium.py`,
`parallel.py`, `fidelity.py`, the analyze, extract, layout, structure,
markdown and epub stages as spec §6 to §8 give them, `cli.py` with the
`galley2epub` command, and their tests.

Out, as spec §12 lists: `wordlist.py`, the correct stage, `galley2epub
edits-from`, the index stage, OCR with Tesseract, figures cut from plates,
and everything the real stage specs will do (running heads, notes,
columns, the style sheet). The EPUB this plan makes keeps running heads,
page numbers and footnotes in the text and has one paragraph per page;
that is the spec, not a defect.

The spec has no open point. Two places where it said too little for a
coding agent (what markdown checks the hash of `blocks.json` against, and
whether extract makes an empty `images/`) were settled in the spec before
the plan was approved.

## What must be in place

Checked by the orchestrator before task 1.1, in the worktree of the plan:

- `pandoc --version` prints `pandoc 3.14` on its first line. The spec's
  statements about Pandoc's behaviour were checked with 3.13 (spec §5,
  §8); Homebrew moved Pandoc to 3.14 on 14 November 2026, and the
  orchestrator checked the same behaviours on 3.14 that day (see the
  report). Another version may behave otherwise.
- `uv run --locked pytest` passes, 5 tests, on the starting commit.
- `uv.lock` holds pdfplumber 0.11.10 and pypdfium2 5.15.2, the versions
  the spec's counts were taken with (spec §2, §11).
- epubcheck, the development tool that validates an EPUB (architecture
  §16): `which epubcheck` prints a path and `epubcheck --version` prints
  `EPUBCheck v5.4.0`. The owner installed it with Homebrew on 14 November
  2026. If it is missing, the tests marked `epubcheck` skip and
  deliverables 3.11 and 4.4 cannot be checked, so the orchestrator stops
  and asks the owner to run `brew install epubcheck`.
- The whole books for the final check, in `samples/public_domain/` of the
  main checkout: `battleofkadeshst00breauoft.pdf` and
  `politicaltheorie00gieruoft.pdf`. They were there on 14 November 2026;
  if not, `uv run python scripts/fetch_samples.py` downloads them.

`tesseract` is installed (5.5.4) but nothing in this plan calls it.

## Streams and the files they may change

Work packages run in order: each starts when every stream of the one
before is merged into `plan/walking-skeleton`. Inside a work package,
the streams below run side by side, each in its own worktree and branch,
as the `following-plans` skill says under "Parallel streams".

| WP | stream | tasks | may change |
|---|---|---|---|
| 1 | `formats` | 1.1-1.4 | `src/galley/errors.py`, `model.py`, `config.py`, `book_folder.py`; `tests/test_errors.py`, `test_model.py`, `test_config.py`, `test_book_folder.py`; `tests/fixtures/model/`, `tests/fixtures/config/` |
| 2 | `pdfium` | 2.1-2.2 | `src/galley/pdfium.py`, `parallel.py`; `tests/test_pdfium.py`, `test_parallel.py` |
| 2 | `fidelity` | 2.3-2.4 | `src/galley/fidelity.py`; `tests/test_fidelity.py`, `tests/fixtures/fidelity/` |
| 3 | `extract` | 3.1-3.2 | `src/galley/analyze/`, `src/galley/extract/`; `tests/test_analyze.py`, `test_extract.py`, `tests/fixtures/analyze/`, `tests/fixtures/extract/`; `tests/conftest.py` |
| 3 | `structure` | 3.3-3.4 | `src/galley/layout/`, `src/galley/structure/`; `tests/test_layout.py`, `test_structure.py`, `tests/fixtures/layout/`, `tests/fixtures/structure/` |
| 3 | `epub` | 3.5-3.6 | `src/galley/markdown/`, `src/galley/epub/` (with `style.css`); `tests/test_markdown.py`, `test_epub.py`, `tests/fixtures/markdown/`, `tests/fixtures/epub/` |
| 4 | `cli` | 4.1-4.2 | `src/galley/cli.py`; `pyproject.toml`, `uv.lock`; `tests/conftest.py`; `tests/test_cli.py`, `test_end_to_end.py` |

The shared files and who changes them:

- `model.py`: stream `formats` only. A later stream that finds it needs a
  change stops and asks the orchestrator, which asks the owner (a change
  to a shared format).
- `pyproject.toml` and `uv.lock`: stream `cli` only, for the
  `[project.scripts]` entry. No stream adds a dependency or a pytest
  marker: `pandoc`, `epubcheck` and `whole_book` are registered already,
  and `thread_unsafe` comes with pytest-run-parallel.
- `tests/conftest.py`: stream `extract` adds the session fixture
  `excerpt_books` (spec §6), running analyze and extract; stream `cli`
  changes it to run the whole pipeline (spec §9). Streams `structure` and
  `epub` do not touch it: their tests use hand-made files.
- `docs/architecture.md` and `docs/glossary.md`: no stream changes them.
- `docs/specs/walking-skeleton.md`: when a task finds a case the spec
  does not settle and the coding skill allows the choice to be written
  into the spec, the stream edits only the section of its own task, in a
  commit of its own, and says so in its answer. A choice that changes a
  format or what a reader of the EPUB sees goes to the owner.

## How the checks below are read

Each deliverable's check names a test file and the least number of tests
`uv run --locked pytest <file> --collect-only -q` must list: one test per
case the spec's "Tests" paragraph for that part lists, a parametrized
case counting once per parameter. A larger count is fine. On the
starting commit (47ad329) none of these files exists, and pytest exits
with 4 (file not found), which was run for each of them on 14 November
2026; a `-k` or `-m` filter that matches nothing exits with 5. Both are
failures. Deliverable 3.9 printed `False` and 3.10 raised
`AttributeError: module 'galley.analyze' has no attribute 'run'` on that
commit. Every work package ends, besides its
deliverables, with the six checks of the `coding` skill passing, read by
their counts: a deliverable whose tests are skipped is not done.

## Work package 1: the data formats

What it gives: the error classes, the formats of every file between
stages with their write and read functions, the book config and the book
folder, complete as spec §3 gives them. Nothing runs on a book yet;
work packages 3 and 4 run these modules on the excerpts.

Stands on: nothing. One stream, `formats`.

Deliverables:

1. The error classes. `tests/test_errors.py` passes and lists at least 2
   tests.
2. The formats. `tests/test_model.py` passes and lists at least 24
   tests: the round trips and byte-identical writes, the JSON of a box
   and of an enum, each malformed-input case of each reader, the extra
   `pages.json` and edits cases, `check_source_pdf` and `block_sha256`
   (spec §3, "model.py", Tests).
3. The config. `tests/test_config.py` passes and lists at least 16
   tests: the two good configs, one per `ConfigError` case, and
   `tesseract_language`.
4. The book folder. `tests/test_book_folder.py` passes and lists at
   least 1 test.
5. `uv run --locked python -c "import galley.errors, galley.model,
   galley.config, galley.book_folder"` exits with 0. On the starting
   commit it fails with `ModuleNotFoundError: No module named
   'galley.errors'`.

Tasks:

- [x] 1.1 Write `errors.py` and `book_folder.py`, with their tests. From
  spec §3, "errors.py" and "book_folder.py", and architecture §5 and §12.
  Serves deliverables 1, 4 and 5.
- [x] 1.2 Write `model.py`: every dataclass and enum, the four JSON
  files' write and read functions with the round-trip tests, and
  `pdf_sha256`, `check_source_pdf`, `block_text` and `block_sha256`. The
  readers rebuild values from good JSON; their checks of bad input are
  task 1.3. From spec §3, "model.py", and architecture §7 and §8. Serves
  deliverables 2 and 5. Needs 1.1 (`InputFileError`).
- [x] 1.3 Make the four readers check their input and stop with
  `InputFileError` at the first problem, and write `write_edits` and
  `read_edits` with their `EditError` cases. From spec §3, "model.py",
  the list under "Reading checks everything" and the edits paragraph.
  Serves deliverable 2. Needs 1.2.
- [x] 1.4 Write `config.py`, with its tests. Its test configs are
  written into `tmp_path` or kept under `tests/fixtures/config/`, with
  absolute paths to the excerpt PDFs. From spec §3, "config.py", and
  architecture §6. Serves deliverables 3 and 5. Needs 1.1 and `Box` from
  1.2.

What could go wrong:

- `frozendict` and `sentinel` are new in Python 3.15, and ty 0.0.104 may
  not know them. A ty error that only an ignore comment would silence is
  a question for the orchestrator, not a `# type: ignore`.
- The readers are the largest piece of the plan: every field of every
  format, with its path in the JSON in the message. 1.3 can grow past a
  day; the orchestrator may split it by file.
- A format that turns out to be wrong in work package 3 comes back here.
  That change is the owner's (a shared format), so it stops the plan.

Review: the four categories of the `reviewing-code` skill. Context for
the reviewers: the formats are complete on purpose, including fields the
skeleton leaves empty (notes, word changes, page numbers, the OCR
audit), because the skeleton is there to try them (spec §3); no stage
uses them yet.

## Work package 2: shared machinery

What it gives: the one thread that calls PDFium, the thread pool that
maps a function over pages, and the fidelity check, complete as spec §4
and §5 give them. Nothing runs on a book through the CLI yet; work
package 3 calls these from the stages and work package 4 runs them on
the excerpts.

Stands on: work package 1. Two streams side by side, `pdfium` (tasks 2.1
and 2.2) and `fidelity` (tasks 2.3 and 2.4).

Deliverables:

1. PDFium in one thread. `tests/test_pdfium.py` passes and lists at
   least 7 tests; `uv run --locked pytest tests/test_pdfium.py -m
   thread_unsafe --collect-only -q` lists at least 6 (every test but the
   one of `strip_stride`).
2. The pool. `tests/test_parallel.py` passes and lists at least 6 tests.
3. The word check. `uv run --locked pytest tests/test_fidelity.py -m
   "not pandoc"` passes and lists at least 11 tests: each boundary with
   equal sides, the lost and invented word, the multiset case, the
   structure cases and the markdown cases of spec §5, Tests.
4. Reading the Markdown with Pandoc. `uv run --locked pytest
   tests/test_fidelity.py -m pandoc -rs` passes, at least 7 tests, none
   skipped.

Tasks:

- [x] 2.1 Write `pdfium.py`, with its tests. From spec §4, "pdfium.py",
  architecture §8 ("RenderedPage") and §12, and the coding skill,
  "Threads and PDFium". Serves deliverable 1. Stream `pdfium`.
- [x] 2.2 Write `parallel.py`, with its tests. From spec §4,
  "parallel.py", and the coding skill, "Threads and PDFium". Serves
  deliverable 2. Stream `pdfium`; independent of 2.1, run after it in
  the same stream.
- [x] 2.3 Write `fidelity.check_stage` for the three boundaries, with its
  unit tests, which build `MarkdownWords` by hand. From spec §5, "The
  words of each side" and the paragraph after it, and architecture §13.
  Serves deliverable 3. Stream `fidelity`.
- [x] 2.4 Write `fidelity.read_markdown`, with its tests marked `pandoc`.
  From spec §5, "Reading the Markdown". Serves deliverable 4. Stream
  `fidelity`; needs `MarkdownWords` from 2.3.

What could go wrong:

- A PDFium object closed by a finalizer in a worker's garbage collection
  instead of in the PDFium thread: it crashes rarely, so the test that
  renders from 6 threads at once may pass while the defect is there. The
  `conventions` reviewer reads every pypdfium2 call for an explicit close.
- pytest-run-parallel runs each test in 8 threads at once; a PDFium test
  left without `thread_unsafe` will still pass, through the PDFium
  thread, but costs 8 times its time.
- Pandoc's JSON may differ from 3.13's in another version; deliverable 4
  then fails on a statement of the spec, which is a question for the
  owner, not a test to loosen.

Review: the four categories, once for both streams after they are
merged. Context for the reviewers: the fidelity check handles removals,
word changes and notes although no stage of the skeleton makes them,
because the real stages will (spec §5); `page_size` is called by no
stage of the skeleton (spec §4).

## Work package 3: the six stages in their simplest form

What it gives: analyze, extract, layout, structure, markdown and epub,
each with its `run` and its pure functions as spec §6 to §8 give them.
analyze and extract run on both excerpts through the session fixture
`excerpt_books`; layout, structure, markdown and epub are tested on
hand-made files, and work package 4 runs them on the excerpts.

Stands on: work packages 1 and 2. Three streams side by side: `extract`
(3.1, 3.2), `structure` (3.3, 3.4) and `epub` (3.5, 3.6). They share no
file, and none needs another's output: each stage reads files in the
formats of `model.py`, and its tests write those files by hand.

Deliverables:

1. analyze. `tests/test_analyze.py` passes and lists at least 8 unit
   tests: the three kinds of page, `require_text_layer` naming both blank
   pages, `ocr = redo`, and the three page indices at the page count
   (spec §6, "Their tests").
2. extract. `tests/test_extract.py` passes and lists at least 4 unit
   tests of `page_words`: the three words around a region and the
   excluded page.
3. analyze and extract on the excerpts. The tests that read
   `excerpt_books` assert the `pages.json` and `words.json` contents spec
   §6 lists for both excerpts, as literals, and pass.
4. The runs of their own. `uv run --locked pytest tests/test_analyze.py
   tests/test_extract.py -m thread_unsafe --collect-only -q` lists at
   least 4 tests, among them the one that compares the files written with
   1 worker and with 6 byte for byte, and they pass.
5. layout. `tests/test_layout.py` passes and lists at least 10 tests:
   `group_lines`, `layout_page`, the 1-against-3-worker run and the
   stale `pages.json` (spec §7, "Their tests").
6. structure. `tests/test_structure.py` passes and lists at least 4
   tests: `page_blocks` and the fidelity check on hand-made inputs and
   outputs, passing and failing.
7. markdown. `uv run --locked pytest tests/test_markdown.py -rs` passes,
   at least 9 tests, none skipped: `escape_markdown`, `render_markdown`
   and the three edits cases of `run` (spec §8, "Their tests").
8. epub. `uv run --locked pytest tests/test_epub.py -m "not epubcheck"
   -rs` passes, at least 4 tests, none skipped: `pandoc_arguments` and
   `run` with and without `book.md`.
9. `src/galley/epub/style.css` exists in the package: `uv run --locked
   python -c "import importlib.resources as r;
   print(r.files('galley.epub').joinpath('style.css').is_file())"`
   prints `True`.
10. Each stage's `run` exists: `uv run --locked python -c "from galley
    import analyze, extract, layout, structure, markdown, epub; [m.run
    for m in (analyze, extract, layout, structure, markdown, epub)]"`
    exits with 0. On the starting commit it fails with `AttributeError`.
11. The hand-written EPUB passes epubcheck. `uv run --locked pytest
    tests/test_epub.py -m epubcheck -rs` passes, 1 test, not skipped.

Tasks:

- [x] 3.1 Write analyze, with its unit tests, and add the session fixture
  `excerpt_books` to `tests/conftest.py`: a book folder per excerpt
  under pytest's temporary directory, with the configs of spec §9, "The
  end-to-end test", on which analyze runs. Add the `pages.json` excerpt
  tests and analyze's runs of their own. From spec §6, "analyze" and
  "Their tests". Serves deliverables 1, 3, 4 and 10. Stream `extract`.
- [x] 3.2 Write extract, with its unit tests; make `excerpt_books` run
  extract after analyze; add the `words.json` excerpt tests and extract's
  runs of their own. From spec §6, "extract" and "Their tests". Serves
  deliverables 2, 3, 4 and 10. Stream `extract`; needs 3.1.
- [x] 3.3 Write layout, with its tests. From spec §7, "layout" and
  "Their tests". Serves deliverables 5 and 10. Stream `structure`.
- [x] 3.4 Write structure, with its tests. From spec §7, "structure" and
  "Their tests". Serves deliverables 6 and 10. Stream `structure`;
  independent of 3.3, run after it.
- [x] 3.5 Write markdown, with its tests. From spec §8, "markdown" and
  "Their tests". Serves deliverables 7 and 10. Stream `epub`.
- [x] 3.6 Write epub and its empty `style.css`, with its tests. From spec
  §8, "epub" and "Their tests". Serves deliverables 8, 9, 10 and 11.
  Stream `epub`; its tests write `book.md` by hand, so it does not need
  3.5.

What could go wrong:

- The 1-against-6-worker comparison of analyze and extract fails when
  results are gathered in completion order, or when a float is written
  differently by two paths (pdfplumber's numbers through `json.dumps`
  only, as spec §3 says). The failure shows only on more pages than
  workers, which the Kadesh excerpt gives.
- The counts of spec §2 and §6 were taken with pdfplumber 0.11.10; a
  different version in `uv.lock` changes them. They are the spec's
  literals, so a mismatch goes to the orchestrator, not into the test.
- layout's centre rule compares floats with the edges included; spec §7
  measured the closest centre at 0.075 pt from an edge on Kadesh, so a
  count that differs by one points at an edge rule written as strict, not
  at rounding.
- markdown and epub depend on Pandoc 3.13's behaviour: escaped
  punctuation read as itself, `--fail-if-warnings`, one chapter file
  `EPUB/text/ch001.xhtml` with the div ids kept (spec §8).
- `excerpt_books` is session-scoped and runs once even under
  `--parallel-threads=8`; a test that runs a stage on a folder of its
  own and is not marked `thread_unsafe` runs 8 times and spends the
  budget of spec §10.

Review: the four categories, once for the three streams after they are
merged, with the two excerpt PDFs. Context for the reviewers: the
skeleton's bad reading order (footnote columns and margin headings read
across a row), Kadesh's plate words kept as a paragraph, and the heavy
escaping of `book.md` are what spec §2, §7 and §8 ask for; the `spec` and
`fidelity` reviewers check that no word is lost, not that the order is
good. The excerpt tests of layout, structure, markdown and epub come in
work package 4.

## Work package 4: the command and the end-to-end test

What it gives: `uv run galley2epub run <book folder>` makes `book.epub`
from a folder with a `book.toml`, through every stage, and the session
fixture runs that command on both excerpts, so that every excerpt test
reads the files of one real run.

Stands on: work packages 1 to 3. One stream, `cli`.

Deliverables:

1. The command is installed. `uv run --locked galley2epub --help` exits
   with 0. On the starting commit it fails: uv cannot find
   `galley2epub` (exit 2).
2. The command's own tests. `tests/test_cli.py` passes and lists at
   least 5 tests: the entry point, the stages one by one against `run`,
   and the three errors of spec §9, "Other tests of this work package".
3. The end-to-end test. `tests/test_end_to_end.py` passes and lists at
   least 5 tests, one for each of `lines.json`, `blocks.json`, `book.md`,
   `book.epub` and the files of the book folder, with the literals spec
   §9 gives, and the tests of deliverables 3.3 and 3.4 still pass on the
   folders of `run`.
4. Both excerpt EPUBs pass epubcheck. `uv run --locked pytest
   tests/test_end_to_end.py -m epubcheck -rs` passes, none skipped.
5. The speed budget. `uv run --locked pytest` and `uv run --locked
   pytest --parallel-threads=8` each finish under 30 s; the report gives
   both times and the five slowest tests pytest prints.

Tasks:

- [x] 4.1 Write `cli.py`, add `[project.scripts]` to `pyproject.toml`
  (and `uv.lock` if `uv lock --check` asks), with the tests of the entry
  point and of the three errors. From spec §9, "cli.py" and "Other tests
  of this work package", and architecture §14. Serves deliverables 1 and
  2.
- [x] 4.2 Change `excerpt_books` to run `main(["run", folder])` on each
  excerpt, and write the end-to-end tests and the test of the stages one
  by one. From spec §9, "The end-to-end test" and "Other tests of this
  work package". Serves deliverables 2 to 5. Needs 4.1.

What could go wrong:

- The budget. The prototype of spec §10 ran the expensive tests in 4.8 s
  on the owner's M5 Pro; the 8-thread run repeats every test not marked
  `thread_unsafe` 8 times. If either run passes 30 s, the orchestrator
  reads `--durations=5`, finds the test in the wrong tier or unmarked,
  and stops for the owner only if no test is at fault.
- The test that runs the stages one by one must give the same bytes as
  `run`; a stage that writes something depending on the time or on the
  folder's path (an absolute path in a file) breaks it.
- The entry-point test runs the script next to `sys.executable`, which
  exists only after `uv sync` installed the package with its new script.

Review: the four categories, with the two excerpt PDFs and the EPUBs of
the session fixture. Context for the reviewers: `correct = true` and the
subcommands `correct` and `edits-from` are refused on purpose (spec §9).

## The final check of the plan

After work package 4 is merged and reviewed, the orchestrator runs these
in the plan's worktree and puts each command and its result in the
report:

1. The six checks of the `coding` skill, with the counts of passed and
   skipped, and the time of each pytest run against the 30 s budget.
2. Both excerpts by hand: a folder under `tmp/` for each, with the
   `book.toml` of spec §9, and `uv run --locked galley2epub run <folder>`.
   Each writes `book.epub`; since layout, structure and markdown run the
   fidelity check before writing, a written `book.md` is the proof that
   the check passed at every boundary. Then `epubcheck <folder>/book.epub`
   on both, with 0 errors.
3. The whole books. The spec gives no `whole_book` test, so `uv run
   pytest -m whole_book` collects nothing (exit 5) and is not this
   check. Instead, a folder under `tmp/` for each whole book with a
   minimal `book.toml`, and `galley2epub run`. analyze stops with
   `PdfError` listing the pages without a text layer (architecture §7b
   counts them); those pages go into `exclude_pages`, as
   the error message says, and the run is repeated. The report gives
   the pages excluded, the time of each run with the machine and
   `--workers`, and epubcheck's result on each EPUB. Kadesh page index
   69 holds printed text and no text layer; excluding it records its
   words as removals, which the skeleton allows, and the report says so.
4. The owner looks at the four EPUBs on the Kindle. That is not a check,
   and the plan is done without it.

The `tmp/` folders are deleted when the report has their results.
