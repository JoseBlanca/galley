---
name: following-plans
description: How an approved implementation plan of galley is carried out. Use it when the owner asks to run, execute, implement or continue a plan under docs/plans/. The session is an orchestrator. It works in a worktree and branch of the plan, sends each task to a subagent, checks what comes back, has each work package reviewed, keeps a work report, and goes on until the plan is done or the owner is needed. It never merges into main.
---

# Following an implementation plan

The session that runs a plan is an orchestrator. It does not write the
code: it sends each task to a subagent, checks what comes back, and
decides what happens next. A plan takes hours, and the details of each
task would fill the orchestrator's context long before the end. What it
keeps is the plan, the state of the work, the decisions and the report.

It goes from one work package to the next until the plan is done, and
stops only when it needs the owner.

## Before the first task

1. The plan is approved and its specs are settled. If not, say so and
   stop.
2. Make the worktree and branch of the plan, from the local `main`:

       git worktree add .claude/worktrees/<plan> -b plan/<plan> main

   then `EnterWorktree` with that path, and `uv sync` inside it. All the
   work of the plan happens there.
3. Check what the plan says must be in place by running it: `which
   pandoc`, the sample PDFs under `samples/` of the main checkout (they are
   not in git, so the worktree reaches them by absolute path). When
   something is missing, tell the owner what and stop. Do not build it on
   the side: that it is not part of this plan was somebody's decision.
4. When `git worktree list` shows another session's worktree, read the
   board, `.claude/board/` of the main checkout (see the README there). A
   message that names a file this plan will change goes to the owner
   before the first task touches it. Post the start message of the plan.
   When no other session is working, the board is skipped.
5. Start the work report and commit it, with the plan's state changed to
   under way.

## One task

Send the task to a `general-purpose` subagent, with a prompt that stands
on its own, because the subagent knows nothing of the session:

- the path of the worktree, and that all its work happens there on the
  branch that is checked out. It is not given `isolation: "worktree"`,
  which would start it from `main`;
- the path of the plan and the number of its task, and that it reads the
  whole work package of that task there. The work package is not copied
  into the prompt;
- the paths of the spec, `docs/architecture.md` and `docs/glossary.md`;
- the skills to follow: `coding`, and `writing` for docstrings and the
  commit message;
- today's date, and that every date it writes is that one. A subagent has
  no clock and works the date out from the files, and gets it wrong;
- what earlier tasks built that it stands on, and what the orchestrator
  knows that the code does not show: an answered open point, a decision
  taken two tasks ago;
- to commit when the checks pass, one commit for the task, and not to
  touch the plan or the report. A change it had to make to the spec is a
  commit of its own, before the code;
- what to send back, in under 300 words: what it built, the commit, the
  last line of each check, what it did differently from the task and why,
  and any question it could not settle.

Tasks the plan marks as able to run side by side go to several subagents
at once only when they touch different files. One writer per file in a
tree.

Several small tasks of one work package can go to one subagent in one
prompt, and a small work package can go whole. A task never goes to a
subagent together with a task of another work package.

## Checking what comes back

What a subagent says is a claim, and a claim the next step rests on is
checked. This costs little context, because it looks at results:

- `git log` and `git status` in the worktree: the commit is there, the
  tree is clean.
- The checks of the `coding` skill, run by the orchestrator, reading their
  last lines. Read the counts in pytest's summary, not only that it
  passed: "5 skipped" may be the whole of the new work.
- What the task said would exist: the named tests, the subcommand, the
  file it writes on the sample.

When the work is not right, the same subagent gets it back with what is
wrong, through `SendMessage`. After a second failure a fresh subagent
gets the task with what was learned. A third failure is a reason to stop
and ask.

Then tick the task in the plan, note it in the report, commit both.

## The end of a work package

1. Run each deliverable's check yourself and put the command and its
   result in the report. A deliverable that does not pass is not done.
2. Have the work package reviewed, as the `reviewing-code` skill says.
3. Evaluate the findings yourself; that judgement is the orchestrator's.
   The fixes go to a subagent, the one that wrote the code when it is
   still there, with the verdict on each finding. It may answer that a
   finding does not hold, with evidence.
4. Run the checks and the deliverables again after the fixes.
5. Write the work package into the report.
6. When other sessions are working, post to the board what this work
   package learned that another session would otherwise find again, and
   any change to a shared file.

## Changing the plan

The orchestrator changes the plan without stopping when the change is
small: tasks split, merged or reordered; a task added inside what the
work package gives; another file than the one named; a check replaced by
one at least as strong. Every change goes into the plan and into the
report with its reason.

It stops for the owner when the change is not small: a deliverable dropped
or its check weakened; a work package added or removed; anything that
changes a spec, a shared format in `model.py`, or what a reader of the
EPUB sees; a task that failed three times; anything outside the worktree
that cannot be undone.

Before stopping, do the work that does not depend on the answer. Leave
the tree with the checks passing and everything committed, update the
report, and ask as the `writing` skill says a decision is asked for.

## The work report

`docs/reports/<plan>.md`, written as the work goes, for the owner, who was
not there. After each work package, a short section:

- Did it finish as planned? Each deliverable with the command that checked
  it and what it gave.
- What changed in the plan, and why.
- What the review found that mattered, what was fixed, and which findings
  were not taken, with the reason in a line.
- What the owner should know: a sample page that behaved unexpectedly, a
  threshold that had to move, a risk for what comes next.
- Under a heading that says it is for whoever next revises a skill or
  writes a plan: what would change a skill or the size of a task. A task
  sent twice and why, a sentence of a skill that misled.

When the plan is done, the top of the report gets what the owner reads
first: whether it is done, what exists now, what is left open, what is
asked of them, which is at least the merge and a look at the EPUBs. The
report goes to the `first-reader` before the owner is told.

## When the plan is done

1. Every task ticked, every deliverable checked, the final check run, the
   plan's state set to done, the report finished, all committed.
2. Tell the owner: the plan is done on branch `plan/<plan>`, the report's
   path, and what it asks of them.
3. Do not merge into `main` and do not push. The order to merge is the
   owner's. After they give it, merge, and run the checks on `main`.
4. After the merge, `ExitWorktree` with `keep`, then
   `git worktree remove .claude/worktrees/<plan>`,
   `git branch -d plan/<plan>`, any reviewer worktree left, and the plan's
   board messages. Something on the branch that was not merged and that
   the owner has to judge (an experiment, a measurement) is not removed:
   say what it is and where.

## When a session ends before the plan

The state is in the repository: the ticks in the plan, the report, the
commits on the branch. A new session enters the worktree, reads the plan
and the report, runs the checks, and goes on from the first task that is
not ticked.
