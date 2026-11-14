# galley

Turns a PDF of a mostly-text book into an EPUB that reflows on a Kindle.
The name is the printer's galley: the typeset text as one continuous
column, before it is cut into pages, which is what gets proofread. galley
takes the pages away again (running heads, page numbers, broken lines and
hyphens) and leaves continuous Markdown to proofread before the EPUB.

The package is `galley`; the command is `galley2epub`. The stages run in
order and pass files to each other:

    analyze → extract → layout → structure → correct (optional) → markdown → epub

Each stage is a subpackage of `src/galley/`. The formats of the files
between stages are defined once, in `src/galley/model.py`, and described
in `docs/architecture.md` (both still to be written). A stage reads the
PDF, the book config and the file of the stage before it, writes one file,
and imports no other stage, so each one can be built and tested on its
own, with fixture files in `tests/`.

## How the assistant works here

The skills are under `.claude/skills/` and the subagents under
`.claude/agents/`:

| work | skill |
|---|---|
| any prose a person reads | `writing` (read first) |
| a spec of a stage, `docs/specs/<stage>.md` | `writing-specs` |
| a plan, `docs/plans/<name>.md` | `writing-plans` |
| carrying out a plan | `following-plans` |
| writing code or tests | `coding` |
| reviewing a work package or a commit | `reviewing-code` |

A document under `docs/`, except a plan, goes to the `first-reader` subagent before it is
handed over, and a spec also to `spec-reviewer`.

A session that writes in the repository, a spec, a plan, a skill or code,
works in a git worktree and branch of its own under `.claude/worktrees/`,
made before its first edit, because two sessions editing the main checkout
at once leave their changes mixed in the same files. When `git worktree
list` shows that another session is working, it reads the messages on the
board, `.claude/board/` (see the README there), before its first edit, and
posts one that says what it works on and which shared files it may change.
Nothing is merged into `main` without the owner's order.

## Replies in chat

The owner reads a reply to decide something or to learn what they need
for their own work, and did not see the session. The `writing` skill
holds in chat, and these are the principles that fail most often there:

- A reply opens with a sentence that says what it is about, then the
  answer in a full sentence. When several things are true, the one that
  changes what the owner does goes first.
- It holds the decisions needed from the owner and what they need to
  know. How the work went stays out unless it changes what they do next.
- A request for a decision has the options, what each costs, and a
  recommendation. What can be decided without the owner is decided.
- No name before its explanation: labels from the session and names of
  files, types and scripts are not words the owner has unless they used
  them first.
- A number where an adjective would go, with what it was measured on.
- What failed or was not done is said as plainly as what worked.

## Environment

- uv for everything: `uv run`, `uv add`, `uv run pytest`, `uv run ruff`,
  `uv run ty check`.
- Python 3.15 free-threaded (`3.15t`, pinned in `.python-version`). A new
  dependency must install on it as a wheel; check with
  `uv pip install --only-binary :all: <pkg>` before adding it. PyMuPDF and
  PyYAML do not, which is why the project uses pypdfium2, pdfplumber and
  TOML.
- Work is parallel by threads. PDFium (pypdfium2) is not thread-safe: every
  call into it runs in one thread, and the rendered images go to the workers.
- Pandoc builds the EPUB; Tesseract does the OCR; epubcheck validates the
  EPUB. All three are Homebrew binaries (epubcheck is not installed yet).
- The checks are listed at the end of the `coding` skill: `uv lock
  --check`, ruff format and check, ty, and pytest, once normally and once
  with 8 threads. ruff, ty and pytest are pinned to exact versions.

## Samples and test speed

The repository is public, so nothing from a copyrighted book is committed.
Development and tests use public-domain scans from the Internet Archive,
which have the same kind of OCR text layer, running heads and footnotes:

- **Excerpts**, about ten pages each, committed under `tests/fixtures/pdf/`
  and cut by `scripts/fetch_samples.py`, which lists the books, the pages
  of each excerpt and what each excerpt covers. A new case is a new excerpt
  added there, not a longer one.
- **Whole books**, in `samples/public_domain/` (ignored by git), downloaded
  by the same script. They are for the slow tests, marked `whole_book`.
- The owner's own PDFs, which may be copyrighted, sit in `samples/` (ignored
  by git) and are used by hand or by `whole_book` tests, never cut into a
  fixture.

The development loop must stay fast: `uv run pytest` runs everything but
the `whole_book` tests and should take seconds, not minutes. The `coding`
skill gives the budget.

Earlier OCR and constrained-correction code worth reusing is in
`~/devel/tomato_history_web_site/tools/ocr_lab/` (`lib/common.py`,
`reocr.py`, `triage.py`, `folio.py`, and `results/NOTE.md` for what failed).
