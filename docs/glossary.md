# Glossary

The names galley uses for the things of its domain, so that every
document, spec and module calls the same thing by the same name. Started
on 14 November 2026 with `docs/architecture.md`; a term a spec needs and
this list lacks is added here.

**block**: a unit of the book's text after structure: a heading, a
paragraph, a quote, a figure or an index entry. It has an id,
`b-p0012-003`, which is its anchor in the EPUB and what an edit names.
Not a "chunk" or an "element".

**book folder**: the folder that holds a book's config, every file the
stages write, and the edits.

**edit**: a change to the text of one block, kept in a file under
`edits/` and applied by the markdown stage. Made by the correct stage, the
owner or an agent. Not a "correction" unless the correct stage made it.

**excerpt**: a PDF of about ten pages cut from a public-domain book and
committed under `tests/fixtures/pdf/`. The fixture of the excerpt tests.

**figure**: a picture in the book, cut from the page render into
`images/`. A **plate** is a page that is mostly a figure.

**fidelity check**: the test, over the whole book, that the words of a
stage's input are the words of its output plus the removals that stage
made, once its word changes and edits are applied: nothing lost, nothing
invented.

**hyphen join**: two parts of a word split at a line end, "repli-" and
"cate", made into one, "replicate". A kind of word change.

**line**: a line of one region of a page, as layout groups the words, left
to right. Not what pdfplumber calls a line, which runs across columns.
Once structure has joined hyphens and paragraphs, the book has no lines,
only blocks.

**margin note**: a short heading printed in the margin beside a paragraph,
as Gierke has on most pages. A block kind.

**note**: a footnote or endnote of the book. Its **marker** is what is
printed in the text and before the note ("8", "*"). A note holds blocks
of its own, which edits can name. A **note reference** is the place in a
block where the marker was printed.

**page index**: the position of a page in the PDF, from 0. **page
number**: what is printed on the page, a string ("47", "xiv"), which may
be missing or come in two sequences.

**reference page**: a page of an excerpt whose expected output the owner
has checked by eye, used as the literal of a test.

**region**: a part of a page whose lines are read one after the other: the
body column, a margin, a column of footnotes, the running head. Found by
layout; what each region is, structure decides.

**removal**: text a stage took out of the book on purpose, with its page,
box and reason: a running head, a page number, a signature mark, an
excluded page or region.

**running head**: the line printed at the top of most pages, the book's,
chapter's or author's name, often with the page number. Not a "header".

**signature mark**: a small printer's mark at the foot of some pages, "I —
2", which tells the binder how sheets are folded. Not text of the book.

**span**: a run of a block's text with one emphasis and, optionally, a
note reference.

**stage**: one of analyze, extract, layout, structure, correct, markdown,
epub. A subpackage of `src/galley/`.

**text of a block**: the concatenation of its spans' text, which an edit
matches against.

**text layer**: the invisible words an OCR program placed over the page
image of a scanned PDF. **text source**: where a page's words come from:
the text layer, galley's own OCR, or none.

**word change**: a change structure makes to words without losing a
letter, recorded for the fidelity check: a hyphen join, or a note marker
split off the word it was glued to ("Greece,1" into "Greece," and "1").

**whole book**: a complete public-domain book in `samples/public_domain/`,
used by the `whole_book` tests.
