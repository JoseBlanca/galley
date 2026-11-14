---
name: writing
description: How prose is written in galley. Use it before writing or revising anything a person will read, a document under docs/, a spec, a plan, a work report, a README, a docstring or a commit message. Chat replies follow the same principles, and the ones that matter most there are in CLAUDE.md.
---

# Writing

## The reader

What is written in galley is read by one of two people.

The first is the owner of the project, a bioinformatician who programs in
Python and Rust and reads books on a Kindle. They know Python, uv,
pytest, Pandoc as a user, and the OCR experiments of
`~/devel/tomato_history_web_site/tools/ocr_lab`. They do not know the
inside of a PDF or of an EPUB: what a text layer is, how a PDF stores
glyphs and their positions, what a ligature or a soft hyphen does to
extracted text, what a Tesseract page segmentation mode is, how an EPUB
is packaged. Such a term gets a sentence that says what it is the first
time a text relies on it.

They were not in the session: they did not see the files that were
opened, the commands that were run, or the names that came up on the way.
So a text starts with a sentence or two of context: what was worked on,
what the question was, where it sits in the project.

The second reader comes later, another session of the assistant or a
contributor. They have only the page and the repository.

Both read to do something: to decide, to build, or to check. A text is
good when its reader gets through it once, without a question and without
opening anything else, and can then do what they came to do.

## Before writing: the sketch

The order of a text is decided before its sentences. Write a sketch
first, a few lines that are not part of the text:

1. The subject in one sentence, with each option or thing named by what
   it is: "whether running heads are found by repetition across pages or
   by their position in the top band of each page".
2. What the reader should know or be able to do at the end, in the words
   you would use with a colleague. When that cannot be said yet, the
   problem is in the thinking.
3. The terms the text needs, each with its definition, in the order of
   first use.
4. The points, one line each, in the order the reader needs them.
5. What is left out, and where it goes.

The opening of the text is the first two lines of the sketch. When the
text is written, find the first use of each term of line 3 and check that
its definition comes before it.

## The principles

### Write the contents, not the name of the category

"The module holds the layout logic" gives the reader nothing. "The module
finds the running heads, joins hyphenated words and decides where a
paragraph ends" does. Logic, machinery, handling, infrastructure and
pipeline are names of bags: write what is in the bag.

An adjective in place of a number is the same fault: fast, most, rare,
good quality. "The text layer of the Turney PDF has 2,927 characters on
page 61 and 4 hyphenated line ends" is a fact. "The text layer is mostly
fine" is not.

### A number comes with what it was measured on

The book, the pages, the machine, the threads, the program and its
version. The date is the one the session was told, never one worked out
from the dates already in a file. A comparison has both sides in the same
units and says which side is better.

### Context before the name

A term that does work in a sentence is explained before that sentence or
inside it. The reader lacks four kinds of names: labels made up during
the session ("the second run"), names from the code (that a class is
called `Block` does not make it a word the reader has), ordinary words
that mean something narrower here (a "line" of the PDF and a line of the
book are different things once hyphens are joined), and notation.

One name for each thing. The names of the things of the domain are those
of `docs/glossary.md`: a running head, not a header; a block, not a
chunk. The glossary chooses the word and the text still explains it.

### What the reader came for goes first

In a document, what it is about and what it decides. In a section, what
the thing does, in words, before the format or the signature. In a reply,
the answer. The work happened in the other order; the text does not.

### Only what the reader can use

For each sentence, what can the reader do with it? These go out: the
story of how the work went; sentences about the text ("briefly", "this
section describes"); sentences about the reader's reaction ("notably",
"surprisingly"); answers to objections nobody raised; verdicts with no
fact ("there is a catch"). Delete the clause; if no fact is lost, it
stays deleted.

Two things stay although they look like the story of the work: a trap
the next person would fall into, and a measurement that closed an
option. They go where the next person will look: the spec of that
module, or `docs/architecture.md`.

A work report has a second reader, whoever next revises a skill or writes
a plan. What that reader needs goes in one section at the end whose
heading says who it is for.

### Everything at its true strength

A choice is written as a choice, with what it serves and what would have
to be true for another option to win. What was measured is kept apart
from what was assumed or read somewhere: "not measured here". A claim
that holds only in part comes with its condition: "on books with a text
layer", "for one-column pages".

### Plain sentences that stand on their own

Short sentences, active verbs, ordinary words. Every count has its noun
and its set: "4 of the 312 pages". Every pronoun has an antecedent the
reader can see. After an edit, read the sentence before and after.

A list for parallel items, a table for measurements, prose for
reasoning. A heading names the subject of its section. Bold only for the
terms a list defines.

## The forms

- **Documents under `docs/`.** The opening says what the document is, its
  date, what it decides, and which documents it relates to.
- **Docstrings.** What the function or class is in the words of the
  domain, the units (points, pixels, page indices from 0 or page numbers
  from 1) and what a caller must know. How it is implemented stays out
  unless the caller sees it.
- **Commit messages.** A subject that says what changed, a body with the
  why and the numbers. Nothing about the session.
- **A recommendation**: what is decided, with the options spelled out;
  the recommendation in a full sentence; the reasons with their numbers;
  what is not known; what is asked of the reader.
- **A request for a decision**: the options, what each gives and takes,
  the recommendation, and what happens next in each case. What the writer
  can decide alone is decided and not asked.

## Before handing a text over

The writer cannot see what is missing from the page, because they know
it. A document under `docs/` goes to the `first-reader` subagent with the
text, one sentence on who reads it and what for, and three to five
questions the reader should be able to answer. Compare its summary and
answers with what was meant; where they differ, the text is wrong. Fix
it, and send it again when the fix was large.

A commit message or a docstring does not go to the subagent. Read it once
more against "Only what the reader can use" and "Context before the
name".

## When a text is sent back

Correct the text, and correct this skill: find the principle that allowed
the failure and revise it where it stands. A new paragraph only when no
principle covers the case. About 150 lines is the size to stay near.
