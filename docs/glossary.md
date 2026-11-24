# Glossary

The names galley uses for the things of its domain, so that every
document, spec and module calls the same thing by the same name. Started
on 14 November 2026 with `docs/architecture.md`; a term a spec needs and
this list lacks is added here.

**back link**: a link from a note back to its reference in the text,
for a reader who followed the reference to the note. markdown makes
the printed marker of a referenced endnote one (`role="doc-backlink"`),
when the marker holds a character other than white space; the epub
stage gives each referenced footnote one, Pandoc's number at the
start of the note (architecture section 9, "Back links").

**block**: a unit of the book's text after structure: a heading, a
paragraph, a quote, verse, a chapter summary, an epigraph, a figure, a
margin note, an index entry, a list item or a contents entry. Its kind says what the text is, never how it looks. It
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
On a text page, the lines next to an in-page figure that open with a
**caption label** ("figure 2.", "MAP vi."), and the rows that follow
them; they too are the text of the figure block, never a paragraph, a
list item or a contents entry.

**caption label**: see caption.

**chapter label**: the line that gives a chapter's number, "CHAPTER
III.", "CHAPITRE II", "ESSAY I.", a spelled number, "Chapter One", or a
roman numeral alone, "IV". With the title under it, it is one heading,
whose `label` it is; it is never a running head, even when it repeats
from chapter to chapter near the top of the page.

**chapter summary**: the list of a chapter's topics printed under its
heading, separated by dashes, as Stubbs prints them ("Terms of Henry's
accession — His character — …"). A block kind of its own, not a quote.

**contents entry**: one entry of a book's printed table of contents, a
block kind: the chapter's number as printed, its **label** ("2.",
"One", "CHAPTER II."), its title, its printed page number, which is
kept and not shown in the EPUB, and its depth, 1 for a chapter and more
for what the contents prints under it, a section or its topics. It is
linked to the heading of the chapter it names when its title matches
one. Its page number is set apart from the title by space or by
**leader dots**, the dots that lead the eye from one to the other,
which structure removes with a record.

**contents junk**: text at the start or end of a contents entry's
title that is not the printer's: a reader's pen mark or a speck read as
text, alone or with the number it was read together with ("-^1.",
"(Tj"), or a page number the OCR misread into the title ("3x3").
structure takes it off by comparing the title with the heading the
entry is linked to, and removes it with a record (structure spec
section 30, rule 11). Printed text, a number, a year, "&c.", is never
junk.

**contents pages**: the pages of a book's printed table of contents,
named in its config (`contents_pages`). structure makes their entries
contents entries, and no heading of them but the title of the contents
("CONTENTS").

**cut-in inset**: how far inside the body column's edge the body lines
beside a cut-in note start or end; Stubbs' is about 60 pt.

**drop capital**: the large first letter of a chapter, two or three
lines tall. Placed by layout as the first word of the first line.

**edit**: a change to the text of one block, kept in a file under
`edits/` and applied by the markdown stage. Made by the correct stage, the
owner or an agent. Not a "correction" unless the correct stage made it.

**epigraph**: a quotation set at the head of a chapter, before its
text, with its **source**, the line that names its author and often the
work or year, printed after a dash or set flush right. A block kind of
its own, `epigraph`, its source a separate part; a verse epigraph keeps
its line breaks. The dash is how the source looks, not its text: it is
removed with a record and written back by the output. Not a quote, which is
quoted inside the text.

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
`images/`. A **plate** is a page that is mostly a figure. An **in-page
figure** is one printed on a text page among its lines.

**figure text**: the words the OCR read inside an in-page figure's
picture: its lettering, its labels and the marks of its shading. The
picture's image shows them, so structure removes them, with a record.

**fluent wrong word**: a wrong word that reads as a real word, so that
nothing on the page shows it is wrong: "Borchardt" for "Brugsch". The
risk of the correct stage, whose vision model writes such words where the
OCR writes visible junk (`docs/specs/correct.md`).

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

**inkless page**: a page of the scan that prints nothing, or only
another page showing through or a patterned endpaper, while its text
layer holds words the OCR invented there ("SP I fiyj." on a blank page).
analyze finds it by the ink under each word on a small render: on an
inkless page at least half the words have none. Its words are removed
with a record (`docs/specs/plates.md` §2b). Not a **blank page**, which
has no text layer at all.

**known word**: a word the word list holds (at least two letters), or a
number; `wordlist.is_known_word` decides. An **unknown word** holds a
letter or a digit and is not known.

**leader dots**: see contents entry.

**letter fragment**: a piece of a printed letter, a descender, the dot
of an "i" or the stem of an "h", that the text layer gives as a word of
its own inside the word it was cut from ("Swabia, ." on Stubbs' page
24). structure removes it, with the reason `letter_fragment`, in a
book where such pieces are common (`docs/specs/structure.md` §35).

**line**: a line of one region of a page, as layout groups the words, left
to right. Not what pdfplumber calls a line, which runs across columns.
Once structure has joined hyphens and paragraphs, the book has no lines,
only blocks.

**list item**: one item of a list that the book prints, a block kind.
Its **list marker**, a dash, a bullet, a number or a letter ("—",
"•", "1.", "(a)"), is kept apart from its text, as its label, so that
the EPUB can show a list. The items of a list are set apart from the
running text by a hanging indent, each marker line at the left and its
continuation lines further in; a paragraph that starts with a number
and is indented as any paragraph is a numbered paragraph, not a list
item.

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

**note group**: the endnotes printed together under one heading, in a
book that collects its notes at the back per chapter and numbers them
from 1 in each chapter; its **group heading** is that heading, the
chapter's number and title ("Chapter 1." and the title, or
"Introduction"), kept with the group's first note. A group's notes are
linked to the references of their own chapter.

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
mark, guide words, a plate's stray words, the figure text of an in-page
figure, the leader dots of a contents entry, an excluded page or
region, a page of the front matter, the words of an inkless page.

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

**spaced punctuation**: a "?", ";", ":" or "!" that the printer set
apart from its word by a space, "subjection ;". structure attaches it
to the word, with a record, in a book not in French, and puts a
no-break space before it in a French one.

**span**: a run of a block's text with one emphasis and, optionally, a
note reference.

**stage**: one of analyze, extract, layout, structure, correct, markdown,
epub. A subpackage of `src/galley/`.

**stray mark**: a line with no letter or digit above the running head
or above the title of a printed contents, a speck of the scan that the OCR read as text (";", "^"); also a
reader's pen mark or a speck read as text before a contents entry's
label or at the start or end of its title. Removed by structure, with a
record.

**text layer**: the invisible words an OCR program placed over the page
image of a scanned PDF. Its characters come in **the PDF's order**, the
order the OCR wrote them, word after word and line after line, which
galley reads them in. **text source**: where a page's words come from:
the text layer, galley's own OCR, or none.

**text of a block**: the concatenation of its spans' text, which an edit
matches against.

**verse**: the lines of a poem, a block kind whose text keeps the
printed line breaks; every other block joins its lines.

**vision model**: a language model that reads images, run on the
owner's Mac by LM Studio; the correct stage has one read each text page.

**whole book**: a complete public-domain book in `samples/public_domain/`,
used by the `whole_book` tests.

**word change**: a change structure makes to words without losing a
letter, recorded for the fidelity check: a hyphen join, a note marker
split off the word it was glued to ("Greece,1" into "Greece," and "1"),
a spaced sign attached, a word glued at a case change split ("theAvre"
into "the" and "Avre"), the dash before an epigraph's source dropped,
or a list item's dash split off its first word ("—The" into "—" and
"The").
