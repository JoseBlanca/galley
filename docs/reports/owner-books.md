# Work report: owner's books

The work of the plan `docs/plans/owner-books.md`, written as it goes, for
the owner. Started on 17 November 2026 on branch `plan/owner-books`.

## Before the first task

The owner approved the scope in chat on 17 November 2026 and asked that
the specs and the plan be written and carried out without waiting for
their review, since they were away. The specs' open points (structure
§27) were settled by the orchestrator: the epigraph's source and the
note group heading are text fields of their block; group headings stay
out of the table of contents; the markdown step writes the source's
dash as text (a Kindle's support for CSS generated text is untested);
the heading rule's costs on Mariéjol are accepted, Stubbs' publisher's
lists are excluded in its config, and Domesday's 4 false headings are
looked at in task 1.6.

Two surveys ground the specs; their notes are outside the repository
because they quote the owner's books.

**The baseline**, `uv run galley-eval run` on `main` at 9715a93 (3 min
41 s), copied to `runs/owner-books-baseline/` of the main checkout. It
equals Review 3's scores of clean-text: Stubbs' margin notes 291 as
margin notes (error rate 0.244), Domesday's 579 (0.138), Stubbs' index
.984 / .963, Domesday's .995 / .998, body error rates .023 / .055 /
.075 / .310 (Haskins, Stubbs, Domesday, Mariéjol), Domesday's notes
whose reference is right 1,278.
