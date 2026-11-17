# Glossary

The names galley uses for the things of its domain, so that every
document, spec and module calls the same thing by the same name. Started
on 14 November 2026 with `docs/architecture.md`; a term a spec needs and
this list lacks is added here.

**block**: a unit of the book's text after structure: a heading, a
paragraph, a quote, verse, a chapter summary, a figure, a margin note or
an index entry. Its kind says what the text is, never how it looks. It
has an id,
`b-p0012-003`, which is its anchor in the EPUB and what an edit names.
Not a "chunk" or an "element".

**body column**: the rectangle of a page that the main text fills, from
its left edge to its right edge. Its width is the same on every page of a
book; its position moves with the scan.

**body measures**: a book's body word height (the median height of a
row's words) and body line pitch (the median distance from the top of
one row to the top of the next), measured on its pages of at least 15
rows by the module `body_measures.py`, which layout and structure share.

**book folder**: the folder that holds a book's config, every file the
stages write, and the edits.

**caption**: the text printed with a picture to name it ("THE MODERN
MOUND OF KADESH"). On a plate it is the text of the plate's figure block.

**chapter label**: the line that gives a chapter's number, "CHAPTER
III.", "CHAPITRE II", "ESSAY I.", or a roman numeral alone, "IV". With
the title under it, it is one heading.

**chapter summary**: the list of a chapter's topics printed under its
heading, separated by dashes, as Stubbs prints them ("Terms of Henry's
accession — His character — …"). A block kind of its own, not a quote.

**contents pages**: the pages of a book's printed table of contents,
named in its config (`contents_pages`), on which structure makes no
heading.

**cut-in inset**: how far inside the body column's edge the body lines
beside a cut-in note start or end; Stubbs' is about 60 pt.

**drop capital**: the large first letter of a chapter, two or three
lines tall. Placed by layout as the first word of the first line.

**edit**: a change to the text of one block, kept in a file under
`edits/` and applied by the markdown stage. Made by the correct stage, the
owner or an agent. Not a "correction" unless the correct stage made it.

**evaluation book**: a book of the evaluation set of
`evaluation/books.toml`: an Internet Archive PDF, the Project Gutenberg
edition made from that scan, and its settings. See
`docs/specs/evaluation.md`.

**excerpt**: a PDF of about ten pages cut from a public-domain book and
committed under `tests/fixtures/pdf/`. The fixture of the excerpt tests.

**fidelity check**: the test, over the whole book, that the words of a
stage's input are the words of its output plus the removals that stage
made, once its word changes and edits are applied: nothing lost, nothing
invented.

**figure**: a picture in the book, cut from the page render into
`images/`. A **plate** is a page that is mostly a figure.

**footnote band**: the footnotes at the foot of a page, set in smaller
type below the body, in one column or two. A region found by layout.

**front matter**: the pages of a book before its text: endpapers,
labels, half-title, title page, publisher's pages, copyright,
dedication. galley finds where it ends, at the preface or the table of
contents, and drops its text pages with a record
(`docs/specs/front-matter.md`). The preface is not front matter.

**glued words**: two or more words of the book that the text layer
gives as one, because the OCR wrote no space between them and the gap
is narrower than pdfplumber's 3 pt ("UpperandLowerNormandy,"). extract
splits them at wide gaps (`docs/specs/extract.md`).

**guide words**: the first letters of the first and last entries of an
index page, printed under its running head ("BUR CON" in Stubbs).
Removed by structure, with a record.

**heading**: a chapter's or a section's title, a block kind with a
level, 1 for a chapter and 2 for a section inside it. The EPUB's table
of contents is made from the headings.

**hyphen join**: two parts of a word split at a line end, "repli-" and
"cate", made into one, "replicate". A kind of word change. When the
book's words show a compound, the hyphen is kept ("Anglo-Saxon"),
recorded as a kept hyphen. A **guessed join** is one that neither the
word list nor the book's own words support; the hyphen is dropped and the
change recorded as guessed, for review.

**index entry**: one entry of a book's printed index, its first line at
the column's left edge and its continuation lines indented (a **hanging
indent**). A block kind. A **sub-entry**, a heading under an entry that
Haskins and Stubbs print inline after a ";" ("Amari, M., 216, 248;
quoted, 234."), is an index entry of its own, of depth 2.

**known word**: a word the word list holds (at least two letters), or a
number; `wordlist.is_known_word` decides. An **unknown word** holds a
letter or a digit and is not known.

**line**: a line of one region of a page, as layout groups the words, left
to right. Not what pdfplumber calls a line, which runs across columns.
Once structure has joined hyphens and paragraphs, the book has no lines,
only blocks.

**margin note**: a short heading printed in the margin beside a paragraph,
as Gierke has on most pages. A block kind. An **outer margin note** is
printed outside the body column (Gierke, Domesday); a **cut-in note**
inside it, at its outer side, with the body lines beside it shortened
(Stubbs).

**note**: a footnote or an endnote of the book. A **footnote** is printed
at the foot of its page; an **endnote** with the others in a section of
their own (Gierke's "NOTES."). Its **marker** is what is printed before
the note ("8", "(3)", "*", "291."). A note holds blocks of its own,
which edits can name. A **note reference** is the place in a block that
refers to the note, printed as the marker is, often as a superscript; the
OCR may read it differently from the marker ("3" for "8"), and it is
still linked when it has a **marker's shape** (at most 4 characters, at
most 3 of them letters or digits and at most 1 a letter) and falls in
the right order.

**note band**: the rows of ink of one printed margin note, found in a
render of the margin; what re-reading reads for an outer margin note.

**page index**: the position of a page in the PDF, from 0. **page
number**: what is printed on the page, a string ("47", "xiv"), which may
be missing or come in two sequences.

**plate**: see figure. Its text layer holds its caption and **stray
words**, what the OCR read in the picture's lines and shading ("^U;L"),
which structure removes as plate text.

**reading score**: of a reading of a region, its known words minus its
unknown words, a word broken by a hyphen at a line end counted once.
How re-reading chooses between the text layer and Tesseract.

**reference page**: a page of an excerpt whose expected output the owner
has checked by eye, used as the literal of a test.

**reference text**: the Project Gutenberg edition of an evaluation book,
read into galley's kinds of blocks and notes, against which the
evaluation tool compares galley's output. Not the same as a reference
page.

**region**: a part of a page whose lines are read one after the other: the
body column, a margin, a column of footnotes, the running head. Found by
layout; what each region is, structure decides.

**removal**: text a stage took out of the book on purpose, with its page,
box and reason: a running head, a page number, a signature mark, a stray
mark, guide words, a plate's stray words, an excluded page or region,
a page of the front matter.

**re-reading**: reading a region of a page again with Tesseract, from a
300-dpi render, and keeping Tesseract's words only where their reading
score is higher than the text layer's, or equal with more known words.
Done by layout, which records
every region it read (`docs/specs/reocr.md`).

**running head**: the line printed at the top of most pages, the book's,
chapter's or author's name, often with the page number. Not a "header".

**signature mark**: a small printer's mark at the foot of some pages, "I —
2", which tells the binder how sheets are folded. Not text of the book.

**small-print page**: a page of 50 words or more on which at least 85
in 100 of the body column's rows of two words or more, below the
running head, are set in small type (their median word height at most
0.85 of the body's): a page printed wholly in small type, as an index
or a bibliographical note. Re-reading reads it whole below its running
head.

**span**: a run of a block's text with one emphasis and, optionally, a
note reference.

**stage**: one of analyze, extract, layout, structure, correct, markdown,
epub. A subpackage of `src/galley/`.

**stray mark**: a line with no letter or digit above the running head, a
speck of the scan that the OCR read as text (";", "^"). Removed by
structure, with a record.

**text layer**: the invisible words an OCR program placed over the page
image of a scanned PDF. Its characters come in **the PDF's order**, the
order the OCR wrote them, word after word and line after line, which
galley reads them in. **text source**: where a page's words come from:
the text layer, galley's own OCR, or none.

**text of a block**: the concatenation of its spans' text, which an edit
matches against.

**verse**: the lines of a poem, a block kind whose text keeps the
printed line breaks; every other block joins its lines.

**whole book**: a complete public-domain book in `samples/public_domain/`,
used by the `whole_book` tests.

**word change**: a change structure makes to words without losing a
letter, recorded for the fidelity check: a hyphen join, or a note marker
split off the word it was glued to ("Greece,1" into "Greece," and "1").
