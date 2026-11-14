# The board

This directory holds the messages that sessions working on galley at
the same time leave for each other. Each session works on its own branch
in its own worktree, so what it commits is invisible to the others until
its branch is merged. The board is outside the branches for that reason:
this README is the only file of the directory in git, and the messages are
reached from every worktree at the same path,
`/Users/jose/devel/book_parser/.claude/board/`.

A message is one markdown file named by the time it was posted, in UTC,
and the branch that posted it, so that `ls` lists them in order:

    2026-11-14T1530-plan-walking-skeleton.md

It is under 15 lines, opens with a sentence that says what it is about,
and is one of:

- **A start**: the plan or spec the session works on, its branch, and the
  shared files it may change: `src/galley/model.py`,
  `docs/architecture.md`, `docs/glossary.md`, `pyproject.toml`.
- **A finding** another session would otherwise find again: something a
  sample PDF does, a trap of a library or of free-threaded Python.
- **A change to a shared file**, when it happens, with what changed.

A message is information, not an order. When two branches will change one
shared file, the session that sees it tells the owner, who orders the
merges.

When a branch is merged or dropped, its messages are removed by the
session that merges. What still matters goes where the next reader looks:
the spec, `docs/architecture.md`, or the work report.
