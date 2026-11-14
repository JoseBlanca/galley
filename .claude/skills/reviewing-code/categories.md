# The categories of a code review

A reviewer reads the section for its category and the parts of
`.claude/skills/coding/SKILL.md` it names. The rules are there with their
reasons; what is here is what to look for and how.

## spec

Does the code do what the spec says, on real pages?

- Go through the spec part by part: the rules, the cases, the open points
  and their "meanwhile". For each statement find the code that makes it
  true and the test that fails if it stops being true. A statement with no
  code, or code with no test, is a finding.
- Run the stage on the reference pages the spec names, and on two or three
  pages of the samples it does not name: a chapter opening, a page of
  notes, the index, a page with an image. Look at the output.
- Look for what the code does that the spec does not say: a threshold, a
  skipped page, an early return. Each is a gap of the spec or a defect of
  the code; say which you think.
- When the code and the spec disagree and the code looks right, the
  finding is about the spec.

## tests

Can each test fail, and are the numbers the change claims true?

- For every test of the change, break the code it guards and run it: flip
  a comparison, drop a branch, return early. A test that still passes
  guards nothing. First show that your change altered the output on some
  input.
- The ways a fixture hides a defect: a condition no fixture reaches; pages
  that are all alike, so that two rules give the same result; one page
  where the rule is about many pages.
- Expected values are literals from the spec or a reference page. A test
  that computes its expectation with the code under test is a finding.
- Parallel code: run with 1 worker and with several, on more pages than
  workers, outputs compared?
- Every number a docstring, a comment or the commit message gives about
  the change (pages, words, seconds) is computed again, not read again.
- Restore the code after each experiment, end with `git status` clean.

## fidelity

The section "No word lost, none invented" of the coding skill. This is
the category that guards the first goal of the project.

- Run the stage on a whole sample book and compare the words of its input
  and its output with the fidelity check. Report each word missing
  without a record, each word that appears and was not in the input, and
  each change of order, with the page.
- Read every path that drops or rewrites text: `continue` in a loop over
  words, lines or pages; a filter; a regex substitution; a hyphen join; a
  `strip`; a Unicode normalisation that changes letters. Is each recorded,
  with a reason?
- Hyphen joins: is the join guarded by a dictionary or the book's own
  words? Find a sample line where a real hyphenated compound ends a line,
  and see what comes out.
- Text from a model: can any reach the output except through the
  `correct` stage and its log?

## conventions

The sections "Functional style", "Errors", "Types, names and defaults",
"The formats between stages", "Threads and PDFium" and "Dependencies and external programs" of
the coding skill, against `docs/architecture.md`, and the docstrings as
`.claude/skills/writing/SKILL.md` asks for them. Ruff and ty already
enforce part of these, and their output is in your prompt: look for what
they cannot see. This reviewer only reads.

Errors:

- For each way the input can be wrong (a missing file, a PDF with no text
  layer, an encrypted PDF, a config with an unknown key, a page range past
  the end), what does the user see? Is it a `GalleyError` whose message
  names the file, the page and the value?
- A missing `tesseract` or `pandoc`: is it found before the work starts?
- An error turned into a default, a page skipped without a record.

Functional style:

- A function that changes its arguments, reads or writes module state, or
  does I/O while also computing something. I/O outside a stage's `run`,
  the CLI, or a function that does only that.
- A value that escapes a function mutable: a `list`, `dict` or `set` in a
  return value or a field, a class with state that changes, a method that
  changes `self`, a stored generator.

Names and interfaces:

- Read every new name as someone who has not seen the code: does it say
  what the value is, in the words of `docs/glossary.md`, the same in every
  stage?
- Signatures against the spec. A default that changes the output: a named
  constant with its source, or hidden in a function body?
- Docstrings: the units (points or pixels, page index or page number), and
  what a caller must know.
- The same logic in two stages, dead code, a public name that could be
  private.

Formats, threads and dependencies:

- A stage that imports another stage, or reads a file the architecture
  does not list for it. JSON written outside `model.py`. A shared format
  changed without `docs/architecture.md`. A `list` or `dict` field in a
  frozen format.
- A call into pypdfium2 outside the one PDFium module, a use of
  pdfplumber's `to_image`, a PDFium object not closed explicitly. A
  pdfplumber `PDF` or `Page` shared between threads.
- Mutable state shared between workers without a lock, a check-then-act on
  a shared dict, a shared iterator, output whose order depends on which
  worker finished first, a worker count that is not the named constant.
- A new dependency: does it install on 3.15t as a wheel, and does
  importing it turn the GIL back on? Is a tool unpinned?
- A subprocess without a timeout, or a program not found with
  `shutil.which` at start-up.
