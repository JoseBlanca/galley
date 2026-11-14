---
name: writing-plans
description: How an implementation plan is written in galley. Use it when writing or revising a document under docs/plans/, which turns one or more settled specs into work packages with deliverables that can be checked, each made of tasks a subagent can carry out. The following-plans skill executes it.
---

# Writing implementation plans

A plan turns settled specs into the order of the work: what is built
first and what after, in which pieces, and how we know each piece is
done. It is carried out by the `following-plans` skill, an orchestrator
that sends each task to a subagent, checks what comes back and goes on,
so a plan has to be something that can be run that way.

A plan decides nothing about the design. When writing it shows that a
spec left something open, the question goes to the owner as an open point
of that spec, and the plan waits or is written around it.

The prose follows the `writing` skill. A plan lives in
`docs/plans/<name>.md`; the name says what it builds, `walking-skeleton`,
`structure-running-heads`, and is also the name of the branch,
`plan/<name>`, and of the report, `docs/reports/<name>.md`.

## No filler

A plan has as many lines as the orchestrator and the subagents need. The
test for a sentence: would the orchestrator, or the subagent of a task,
do something different without it? What repeats the spec (formats,
thresholds, cases, signatures) is pointed to and not copied, because a
copy is wrong as soon as the spec changes.

## Before writing

- The specs exist and the owner has settled them, or each open point has
  a "meanwhile". Every task has a spec behind it. When a task needs
  something no spec says, a spec is written first; the plan does not
  stand in for it.
- Read the specs, `docs/architecture.md`, `docs/glossary.md`, and the code
  that exists. A plan written without looking at the code plans work that
  is done, or builds on something that is not there.
- Run what the checks will run, once: the CLI command on a sample, `which
  pandoc`, `which tesseract`, `which epubcheck`. A program that is not
  installed is something that must be in place, listed in the plan.
- Show the owner the breakdown in chat before writing the plan: the work
  packages in order, what each gives, what it stands on, how many tasks,
  and what is left out. The owner corrects ten lines faster than a
  finished plan.

## Work packages

A work package ends with something that exists and can be run: the
`extract` subcommand writes `lines.json` for the Turney sample; the EPUB
of the Haynes sample passes `epubcheck` and Pandoc's table of contents has
its chapters. How it looks on the Kindle is for the owner, at the end of
the plan, and is not a check. When it is done the project works, with every check of the
`coding` skill passing.

A work package goes as far as the CLI, so that it can be run on a sample
book. One that stops inside a module, a helper another stage will call,
says so and says which later work package runs it on a book.

Each work package has:

- **What it gives**, in a sentence or two, as the owner would run it.
- **Its deliverables, each with the check that proves it.** The check is
  a command that can fail: the tests of a part of the spec, named by that
  part and counted ("the 6 tests of 'Running heads' pass;
  `uv run pytest -k running_head --collect-only -q` lists 6"); the CLI on
  a sample and what to look for in its output; the fidelity check on a
  whole book. "Running heads are removed" is not a deliverable. A check
  fails on the commit the work starts from, because the thing is not
  there yet. pytest exits with 5 when `-k` matches nothing, and a check
  that is already true before the work checks nothing.
- **What it stands on**: earlier work packages, and what must be in place.
- **Its tasks.**
- **What could go wrong**, when something is known: the thinnest part of
  the spec, a sample page nobody has looked at.

Put first the work package that would change the plan if it failed. The
first plan of the project is the walking skeleton: every stage, in its
simplest form, run end to end on one sample, so that the formats between
stages are tested on a real book before several sessions build on them.

## Tasks

A task is the unit given to a subagent, which starts with nothing but the
skills, the spec and the plan. It reads the whole work package of its
task in the plan, so a task is a few lines and repeats nothing of its
work package. It says:

- what is built and where, the module and the files;
- the part of the spec it is built from, by its heading and path;
- which deliverables of the work package it serves, by number;
- what it needs from earlier tasks.

A task is between an hour and a day of a person's work. A smaller one is
part of its neighbour.

Tasks that touch different files and do not need each other are marked
as able to run side by side, and so are work packages of different
stages: this is what the file formats between stages are for. Two tasks
that change `model.py`, `docs/architecture.md` or `docs/glossary.md` never
run side by side.

## The shape of the document

1. The opening: what the plan builds, from which specs (paths), the date,
   and the state: draft, approved, under way, done.
2. In and out: what is built, and what a reader could expect and is not.
   The open points of the specs that are not answered, each with the task
   its answer would change.
3. What must be in place before the first task, in a form that can be
   checked.
4. The work packages in order, numbered, with tasks numbered inside them
   and a box the orchestrator ticks: `- [ ] 2.3 Join hyphenated words`.
5. How the whole plan is checked at the end, when that is more than its
   work packages: the EPUB of both samples, built and opened, and the
   pages the owner should look at on the Kindle.

A plan says what and in what order, not how. No code and no signatures,
which are in the spec.

## Before handing it over

- Every task names its spec part. Every deliverable has a check that can
  fail and was run on the starting commit, or the plan says why not.
- Could a subagent that reads only one task, the spec and the skills do
  it? Read two tasks that way.
- Nothing in the plan decides what a spec left to the owner.
- The owner approved the breakdown in chat, so a plan does not go to the
  `first-reader`. Read it once yourself as the orchestrator: what is the
  first thing to do, how do I know work package 2 is done.
- The owner approves the plan before it is run.
