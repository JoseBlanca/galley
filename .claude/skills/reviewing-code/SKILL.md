---
name: reviewing-code
description: How code is reviewed in galley and what is done with the findings. Use it after the tasks of a work package are committed and before the work package is reported as done, or when the owner asks for a review of a commit, a branch or a stage. The session sends one code-reviewer subagent per category, each with a fresh context, then evaluates every finding and has the ones that hold fixed.
---

# Reviewing code

The writer of a piece of code cannot review it: they know what it was
meant to do and read that into it. So the review is done by subagents that
start with nothing but the code, the spec and the `coding` skill, one per
category, and the session that asked for the review is the orchestrator:
it sends them out and acts on what they find.

## Before sending the reviewers

1. Fix the scope: a commit or a range, and from it the files and functions
   that changed. The review is of what changed, of what calls it and what
   it calls.
2. Find the spec part and the plan task the change was made from.
3. Run the checks of the `coding` skill once and keep the output, so that
   no reviewer spends its time finding what ruff prints.
4. Note what the reviewers cannot know from the code: an open point the
   owner answered, a later task that adds what looks missing. Most wrong
   findings come from missing context.

## The categories

Each is described in `categories.md`, beside this file. Send every one
that applies, in parallel, in one message.

| category | applies when |
|---|---|
| `spec` | always: the code against the spec, run on the sample pages |
| `tests` | always: can each test fail, are the claimed numbers true |
| `fidelity` | always: can a word be lost, duplicated, reordered or invented |
| `errors` | always: what a user sees when an input is wrong |
| `api` | the change adds or alters functions, names, defaults, docstrings |
| `architecture` | the change touches the formats, `model.py`, threads, PDFium, a dependency, a subprocess |

The subagent is `code-reviewer`. Its prompt gives the category, the
commit under review, the files in scope, the path of the spec, the output
of the checks, the paths of the sample PDFs, and the context of step 4.
`spec`, `tests` and `fidelity` change code to see what happens, so they
are sent with `isolation: "worktree"`, each in its own tree; the prompt
tells the reviewer to check out the commit under review and confirm it
with `git rev-parse HEAD`, and to run `uv sync` there. The others only
read and share the checkout.

## Acting on the findings

The orchestrator acts on the reports; it does not hand the owner a list.

A finding is taken seriously: the reviewer read the code as its next
maintainer will, and often ran the case. It is not set aside because it
is inconvenient. Nor is it the law: a reviewer can lack context, misread
a line, or suggest a worse fix than another. So each finding is checked:

1. Open the line, run the case, read the spec part it cites.
2. Decide:
   - It holds: fix it, with a test that fails first. The suggested fix is
     a suggestion.
   - It holds and the fix is the owner's, because it changes a shared
     format or what a reader of the EPUB sees: a question to the owner,
     with a recommendation.
   - It holds and belongs to a later task or plan: a line in the report
     and in the plan, so that it is not lost.
   - It does not hold: say why, with what was checked and what the reviewer
     lacked. A reason the reviewer would accept if it saw it.
3. A finding about lost or invented text is never closed on a doubt. When
   it can be neither confirmed nor refuted, send the reviewer the missing
   context and ask again, or ask the owner.

Fix one finding at a time with the smallest change. A fix that fails its
checks is reverted whole. When all are handled, run all the checks again.
Two reviewers reporting the same thing from different sides is evidence,
handled once.

When a finding shows that the `coding` skill, the spec or the plan allowed
the defect, that document is corrected too.

## What the owner gets

When the review was asked by the owner, a reply in chat: what was
reviewed, what was found that mattered and is fixed, each finding not
taken with its reason in a line, and what needs them. Within a plan, the
same goes into the work report.
