# The evaluation tool

The evaluation tool measures how far galley's output for a book is from
a human-proofread text of the same scan. It is how galley's quality is
measured and how its bugs are found. For each book of an evaluation set,
it takes three things:

- the Internet Archive PDF;
- the Project Gutenberg edition that Distributed Proofreaders made from
  that scan;
- galley's output for that PDF.

It compares the output of four of galley's stages with the Gutenberg
text, and writes:

- **a scorecard**: the scores of the book's text and of its structure;
- **a list of differences**: each difference with its PDF page and the
  first stage where it appears, for a person or an agent to sort into
  bugs and new features;
- **a table of pages**: for each page, how bad its OCR really is next to
  statistics that galley can compute without a reference, from which a
  detector of bad OCR is chosen;
- a summary of these for a person.

The tool is for development only. It reads galley's files and galley
never imports it, as epubcheck is only a development tool
(architecture §16).

Dated 15 November 2026. It builds on `docs/architecture.md` and
`docs/glossary.md`; "architecture §8" is a section of that document,
"section 6" a section of this spec. No code of the tool exists. galley
exists as the walking skeleton (`docs/specs/walking-skeleton.md`), whose
stages are in their simplest form: one paragraph per page, nothing
removed, no notes. Every measurement in this spec was taken on 15
November 2026 on an Apple M5 Pro, with Python 3.15.0, Pandoc 3.14 and
Tesseract 5.5.4, on galley at commit 636b104.

The owner decided in chat on 15 November 2026:

- **Separate tool:** it is a separate tool, not a subcommand of
  `galley2epub`.
- **One comparison per stage:** it compares the output of each stage, not
  only the final book, so that each difference points at the stage to
  fix.
- **Compared with the corrected text:** the reference is Gutenberg's text
  as its transcribers corrected it. Printer's errors that Gutenberg fixed
  count as differences.
- **A detector of bad OCR for real work:** the tool's table of pages is
  used to find, and test, a statistic that tells galley, with no
  reference, when a page's OCR is bad enough to OCR it again (section 8).

## 1. Terms

The first two are added to the glossary; the others are used only in
this spec.

- **Reference text**: the Gutenberg HTML edition of a book, read into
  galley's kinds of blocks and notes by the rules of section 4.
- **Evaluation book**: a book of the evaluation set: its Internet Archive
  PDF, its Gutenberg edition, and the settings of section 3.
- **Token**: a word as galley's fidelity check splits words, on white
  space (architecture §13). The reference is split the same way.
- **Alignment key**: the form of a token used to align the two texts:
  1. decomposed (Unicode NFKD), with accents and other combining marks
     dropped;
  2. lower case;
  3. `æ`, `œ`, `ð` and `þ` spelled `ae`, `oe`, `d` and `th`;
  4. only letters and digits kept.

  "Pamphlets," and "pamphlets" have the same key; "Æthelred" and
  "AEthelred" too; "pamphletspublishedon" has another.
- **Stage output**: one of the four texts the tool compares, each the
  file a stage writes, in the order galley makes them:

  | output | file | made by | what it shows |
  |---|---|---|---|
  | words | `words.json` | analyze and extract | what the text layer, or galley's own OCR, read on each page |
  | lines | `lines.json` | layout | the same words in reading order: columns, margins and footnote columns separated |
  | blocks | `blocks.json` | structure | the book as blocks and notes, with running heads and page numbers removed and hyphens joined |
  | markdown | `book.md` | markdown | the text the EPUB is built from, with the edits under `edits/` applied |

- **Part**: what a reference block belongs to, for the scores: the body,
  the notes, the index, tables, or figure captions (section 6).
- **Difference**: a place where a stage output and the reference
  disagree after alignment (section 5).

Page always means a PDF page, given by its page index from 0, unless it
says "printed page".

## 2. What the first look found

Each fact below was measured on the four books of section 3. Where a
number was measured another way than this spec defines, it says how.

- **Page anchors.** Gutenberg's HTML keeps the printed page numbers as
  anchors in three of the four books: Haskins 260, Stubbs 322, Domesday
  537. Mariéjol has none. An anchor sits at the word where the printed
  page breaks, mid-paragraph in 183 of Haskins' 260. The plain-text
  edition has no page anchors, which is why the reference is the HTML
  edition.
- **Paragraphs join across pages.** Gutenberg joins a paragraph that
  runs over a page break, and joins a word hyphenated across the break,
  with the anchor after it. In Domesday 11 anchors fall inside a word:
  10 in a joined word (`house<a/>holders`), and one where a space is
  missing (`testamentary<a/>power`).
- **From a printed page to a PDF page.** The PDF page index minus the
  printed page number is constant over runs of pages. It steps where
  plates or blank pages were inserted:
  - Domesday: 25 for 495 of 527 anchors, 21 before the inserted plates;
  - Haskins: 15 for 250 of 260;
  - Stubbs: 21 and 17.

  Fifteen of Domesday's anchors give 24: the first word after the anchor
  was aligned to a word on the page before.
- **Footnotes are moved and renumbered.** Haskins and Domesday gather the
  footnotes at the end of the book; Mariéjol places each after its
  paragraph. All three number them through the book, while the print
  numbers them per page. A note can only be matched by its content. Both
  sides keep the notes in the order of the book.
- **Margin notes.** Stubbs keeps its 467 margin notes between paragraphs.
  Domesday's transcriber moved its 593 to the start of each paragraph
  (590 `p.sidenote` and 3 `span.sidenote`, besides one inside the
  transcriber's note), so their place in the reference is not where
  they were printed.
- **The markup differs from book to book.** Domesday's 1,729 notes are
  `p` elements inside one `div.footnote`; Haskins' 72 are one
  `div.footnote` each; Mariéjol's 1,432 are one `blockquote.footnote`
  each. Stubbs' index is a `ul.index`, Domesday's a `ul.IX`. The `id`
  that pairs a note with its reference is on an `a` inside the note in
  three books, in Haskins on the note's label. One of Domesday's notes
  has a second paragraph, a centred formula. Domesday's notes hold 14
  links to other notes ("p. 54, note 175"), which are cross-references,
  not note references. Gutenberg's own text sits in the body: Domesday
  opens with a paragraph and a table of its own before the title, and
  Mariéjol labels each note "Note 1:" and "(retour)", the link back to
  its reference. One set of rules for every book does not fit; section
  4 gives each book its own.
- **What Pandoc drops.** `pandoc -f html` drops what the comparison
  needs: Domesday's `p.sidenote` class, the class of Mariéjol's footnote
  blockquotes, and the `title` of Domesday's 10 unnumbered page anchors.
  Python's `html.parser` keeps every class and attribute, and reads
  Domesday's HTML in 0.14 s.
- **galley's runs.** galley runs on all four books once the pages without
  a text layer are excluded: 11, 19, 12 and 11 pages. They are blank,
  except Stubbs page indices 9, 52 and 54, which are maps with
  captions. The walking skeleton stops on such pages until analyze has
  its OCR audit. A run takes 4.1 s (Haskins, 280 pages), 5.8 s (Stubbs,
  344), 15.1 s (Domesday, 558) and 15.0 s (Mariéjol, 460), with 6
  workers.
- **Aligning a whole book.** On Domesday, galley's 250,249 tokens against
  the 242,812 of the plain-text edition:

  | method | time | reference tokens aligned to an equal key |
  |---|---|---|
  | `difflib.SequenceMatcher` over the whole book | 130.7 s | 71.8% |
  | two anchored passes (section 5's first two, roughly) | 0.26 s | 92.9% |

  Against the HTML edition, the same two passes align 92.7% in Domesday,
  90.1% in Haskins, 87.4% in Stubbs and 73.7% in Mariéjol. Both were
  measured by a research script whose key kept accents and whose second
  pass aligned all the leftovers of both sides at once; section 5's
  three passes are expected to align as much or more.
- **Gutenberg's own changes to the text.**
  - Haskins' transcriber made spelling, punctuation and hyphenation
    consistent without saying where.
  - Stubbs changed minor punctuation "without notice".
  - Gutenberg leaves out Mariéjol's bibliography (page indices 14–16).
  - Gutenberg adds headings the print does not have: "FOOTNOTES" in
    Haskins, "NOTES" in Domesday.
  - Only Domesday marks corrections in the text: 3 `<ins
    class="correction" title="original: …">`.
- **Characters and conventions.** Domesday's reference has `Æ` 196
  times, `ð` 71 and `þ` 37; galley's text layer has none of them. Haskins
  and Domesday use `’`, `“ ”`, `–` and `—`; Mariéjol uses `'` (14,193)
  and `--` (404). The text layer has `'`, `"` and `—`, and writes number
  ranges with a hyphen, "541-90", where the reference has `–`.
- **Scrambled pages.** Some pages come out of the text layer scrambled
  into single letters, while each letter is still a dictionary word:
  Stubbs' two-column index, page indices 312–321, and Domesday's rotated
  table headers, page index 481.

## 3. The evaluation set

The set is listed in `evaluation/books.toml`, committed. Each entry
gives:

- a short `name`, used for the folder;
- the Gutenberg ebook number and the Internet Archive identifier;
- the `title`, `authors` and `language` that galley's `book.toml` needs;
- `exclude_pages`, the pages without a text layer, checked by eye;
- the reading rules of section 4;
- `not_in_reference`, the page indices whose text Gutenberg left out
  (Mariéjol: 14–16);
- `margin_notes_moved`, true when Gutenberg moved the margin notes, so
  that their position is not scored (Domesday);
- `html_sha256`: the SHA-256 of the HTML file the rules and counts were
  written for. Gutenberg may publish a new version of a book; the reader
  stops with an error when the file differs, so that the counts are not
  silently wrong;
- `expected_counts`: the number of notes, margin notes, note references,
  page anchors and headings the reader must find, and the first five
  tokens of the body, checked by a test (section 10).
  They are counted from the HTML by hand, with a search for each class,
  when the entry is written, never by running the reader.

The first four books (owner, 15 November 2026):

| name | book | Gutenberg | Internet Archive | what it tests |
|---|---|---|---|---|
| haskins | Haskins, *The Normans in European History*, 1915 | 72514 | `normansineuropea00hask` | 72 footnotes, running heads, index; the cleanest text layer |
| stubbs | Stubbs, *The Early Plantagenets*, 1900 | 70828 | `earlyplantagenet01stub` | 467 margin notes, no footnotes, running heads with dates, a scrambled index |
| domesday | Maitland, *Domesday Book and Beyond*, 1897 | 43255 | `domesdaybook00maituoft` | 1,729 footnotes, 593 margin notes, Latin, about 46 tables |
| mariejol | Mariéjol, *Catherine de Médicis*, 1920, French | 36315 | `catherinedemedic00mariuoft` | 1,432 footnotes, a text layer with many misread letters |

Three more books were found and checked to be the same edition as their
scans: Vinogradoff's *Villainage in England*, Bryce's *The Holy Roman
Empire* and Round's *Geoffrey de Mandeville*. They test two-column
footnotes, blackletter running heads and Greek, and are added when a
stage needs them. Adding a book means writing its reading rules, which
takes a look at its HTML.

`scripts/fetch_samples.py` reads `books.toml` and downloads the PDFs to
`samples/public_domain/` and the HTML editions to
`samples/public_domain/gutenberg/pg<n>-images.html` (both ignored by git).

`exclude_pages` lists the pages that have no text layer, because the
walking skeleton stops on them. When analyze has its OCR audit
(architecture §7b), the lists are emptied, and Stubbs' map captions are
then read by Tesseract and compared like any other text.

## 4. Reading the reference

The reference is read from the HTML with Python's `html.parser`, by the
book's reading rules. It becomes the things blocks.json holds:

- **body blocks** in order, each with its kind: heading, paragraph,
  quote, figure, margin note, index entry, or table;
- **notes** in order, each with its blocks;
- the **places of the note references** in the body, each with the note
  it points to;
- the **page anchors**, each with its printed page number, placed
  between two tokens.

### The rules

A rule names elements with a selector of the form `tag.class`, `tag`,
`.class`, or two of these joined by `>` for a child. A book's entry has
one list of selectors for each of these:

| rule | what it matches | the four books |
|---|---|---|
| `start` | reading starts at the first element that matches; what comes before is left out | by default the first element after `header.pg-boilerplate`; Domesday starts at its title, after Gutenberg's own paragraph and table |
| `drop` | elements whose text is left out, with everything inside them | the licence (`footer.pg-boilerplate`), transcriber's notes (`div.transnote`), Gutenberg's headings (`.footnotes > h2`: "FOOTNOTES", "NOTES"), note labels (`a.label`, `span.label`), the asterisks Haskins puts at a section break, where the print has a blank line (`div.tb`, 34), and the "[Larger map]" links of Domesday's maps (`div.larger-version`) |
| `drop_text` | text left out wherever it occurs, given as regular expressions that match a whole run of text | Mariéjol `Note \d+:?` (note 230 has no colon) and `\(retour\)` |
| `separate` | inline elements whose start and end separate words, as a space would | Stubbs' table of contents, whose page column `span.float-right` follows the title with no space ("years’ work<span…>Page"); without the rule the reader would make "workPage" |
| `page_anchor` | page anchors; the number from `id="Page_N"`, else from `title` | `span.pagenum`, `a.pagenum`; their own text, "47" or "[Pg 47]", is dropped |
| `heading` | headings | `h1`–`h6`; Stubbs adds `p.ph3` |
| `margin_note` | margin notes | `div.sidenote`, `p.sidenote`, `span.sidenote` |
| `notes_section` | the part of the page that holds the notes | Domesday `div.footnote`; the others none |
| `note` | one note | Haskins `div.footnote`, Mariéjol `blockquote.footnote`; Domesday none: inside its notes section, a note starts at each element that holds an `id` some note reference points to, and an element without one, such as the centred formula, continues the note before it |
| `note_reference` | an `a` outside the notes whose `href` matches a regular expression | Haskins and Domesday `#Footnote_\d+`; Mariéjol `#footnote\d+`, which leaves out the "(retour)" links to `#footnotetag…`. A link of the same form inside a note is a cross-reference, and its text stays as tokens |
| `quote` | quotes and verse | `div.blockquot`, `div.quote`, `p.quote`, `div.poem`, `div.poetry`, `div.verse` |
| `index` | the index; each `li` inside is an index entry | `div.index`, `ul.index`, `ul.IX` |
| `figure` | figures; the caption is the figure's text | `figure`, `div.figcenter` |
| `table` | tables outside the index | `table` |

Each list has defaults, those of the table; a book's entry adds to them
or replaces them.

- **Which rule wins.** The outermost element that a rule matches owns
  everything inside it: a `p` inside a `div.sidenote` is part of the
  margin note. Four things are found inside any element: page anchors,
  note references, `drop` and `drop_text`. Any element with text of its
  own that no rule matches and that is inside no block is a paragraph,
  whatever its tag; text outside every block, at the top of the document,
  is an error that names its line.
- **Notes.** A note is paired with its reference by the `id` its
  reference's `href` points to, which may be on the note or on any
  element inside it, a dropped label included: `drop` leaves out text,
  not `id`s. A note is matched to its reference by that `id`, never by
  its number.
- **A margin note inside a paragraph**, as Domesday's 3 `span.sidenote`,
  is a block of its own placed before that paragraph, whose text runs on
  around it. Only margin notes move: another block inside a paragraph,
  such as the verse inside Mariéjol's note 1423, ends the paragraph
  where it stands, and the text after it is a new paragraph, so that the
  order of the words is the book's.
- **Text between two notes**, left there by a misplaced end tag (after
  Domesday's note 101, `</p>.’]`), runs on into the last block of the
  note before it, with no space when it starts with punctuation:
  "interlined.’]" stays one token.
- **A page anchor inside the notes**, as Domesday's anchor of printed
  page 357 between notes 1198 and 1199, is out of its place: it is not
  used for pages (section 5), and `summary.md` lists it.
- **Paragraphs.** Any other `p`, or `div` with text of its own, is a
  paragraph. An element left with no token, such as a `p` that holds
  only a page anchor (36 in Haskins, 47 in Stubbs), is not a block.

### Tokens

- The reference's text is split into tokens on white space. A token
  keeps Gutenberg's text, with its accents, curly quotes and dashes.
  `<br>` is a space.
- An anchor inside a word is placed after the whole word.
- The text of a note reference is Gutenberg's number, not a word of the
  book, and is not a token.
- An element of Gutenberg's typographic markup gives its text only:
  small capitals, superscripts, `span[lang]`. "M^{r}" is "Mr".
- A fraction written with a superscript, the fraction slash `⁄` and a
  subscript, `2<sup>1</sup>⁄<sub>2</sub>`, is written as printed, "2½",
  with the Unicode fraction character when there is one, else as
  "2 1⁄2" with a space. Domesday has 94 of them; read as their text only,
  "21⁄2" would be another number.
- A soft hyphen (U+00AD) is removed, and a zero-width space (U+200B)
  separates words. None is in the four books.
- A correction marked in the text (`<ins class="correction"
  title="original: …">`) keeps the corrected text. Its tokens are tagged,
  so that a difference on them is reported as `reference_correction`
  (section 5).

## 5. Comparing a stage output with the reference

Each stage output is compared with the reference in the same way.
Words is compared first, because the page of every reference token comes
from it.

### galley's tokens

A token of galley's side knows its page index. In lines, blocks and
markdown, it also knows the stream it is in: the body, a note, or a
margin note.

- **words**: every word of `words.json`, page by page, in the file's
  order.
- **lines**: every word of `lines.json`, page by page, region by region,
  line by line.
- **blocks**: the tokens of each block, split from its spans one by one
  as the fidelity check splits them (architecture §13). The body blocks
  are one stream in order; the notes, in order, a second; the margin
  notes a third. A token's page is the page of the same word in
  `lines.json`, found by aligning each block with the lines of the pages
  in its `origin`. A block that runs over two pages thus has tokens on
  both. A token made by a word change, such as "replicate" from
  "repli-" and "cate", has the page of the first word it was made from.
  A note reference span, and the `marker` of a note whose `referenced` is
  true, are not tokens, as in the fidelity check at the markdown
  boundary. The marker of an unreferenced note is a word of the book,
  which markdown prints before the note (architecture §9): its words are
  the first tokens of the note's first block.
- **markdown**: `book.md` read by `galley.fidelity.read_markdown`, the
  public function with which the markdown stage's fidelity check reads
  it. Each word comes with its block id, so it has the stream and pages
  of that block in blocks.

**Book order**, used below, is the order of galley's tokens by page
index, and within a page by stream, body first, then margin notes, then
notes, and by position in the stream.

A token of words or lines on the first or last line of its page in
`lines.json` that holds a token with a non-empty alignment key is
flagged `edge_of_page`, since running heads, page numbers and signature
marks sit there. A line of marks only above the running head, a "!" or
";" from a speck on the scan (93 of Stubbs' 324 pages), is flagged too,
and does not take the flag from the line under it.

### Alignment

An **anchored pass** aligns two sequences of tokens:

1. It finds the tokens whose alignment key occurs exactly once in each of
   the two sequences. A token whose key is empty, a mark of punctuation
   only such as "—" or "*", is never an anchor.
2. It keeps the longest subsequence of those that is in the same order on
   both sides.
3. It aligns the stretches between consecutive anchors with
   `difflib.SequenceMatcher(autojunk=False)`, over alignment keys.

A galley token is aligned to at most one reference token. Three passes:

1. galley's body stream against the reference's body tokens, without the
   reference's margin notes. At words and lines, galley's whole text is
   the body stream.
2. The galley tokens still unaligned against the reference's notes; then
   those still unaligned against the reference's margin notes of the
   body. This finds a note wherever each side put it, at the end of a
   chapter or among the words of its page.
3. Whatever is still unaligned on each side, against each other, both
   sides in book order: the reference's tokens by provisional page, then
   in the order of the reference. This finds, for instance, a margin note
   that galley put among the notes, or a footnote's words galley left on
   its page.

Passes 2 and 3 work **near the page**. Each reference token has a
provisional page from what the passes before it aligned: a note's, the
page of its note reference; a margin note's, the page of the first
aligned token of the paragraph it precedes; any other token's, the page
of the nearest aligned token before it. A reference token is aligned
only with galley tokens within one page of its provisional page, in book
order, and those on its provisional page first: the pages either side
are offered only the tokens still unaligned after that. Without the
preference, on Haskins' printed page 119 the reference's "VII," was
paired with "ii8", the page number of the page before, and galley's
"VH," on the right page was left extra. Without the window, the leftovers of the whole book form one sequence,
and a word missing on page 9 was paired with stray marks on page 1: 247
such pairs in Haskins, 537 in Mariéjol, in the first build. A note or
margin note that runs over a page break has its tokens on the page of
its start and the next, within the window.

In difflib's result, an equal stretch gives aligned pairs. A replaced
stretch is examined as "Differences" below says. A deleted or
inserted stretch gives tokens with no partner.

A book whose words output aligns less than 50% of its reference tokens
to a galley token with the same alignment key (`matched`, or `changed`
with an equal key) stops with an error that gives the share, because a wrong scan or a
broken reading rule is likelier than galley being that far off. 50% is
a guess, under Mariéjol's 76.0% in the first build.

### Pages

Every reference token gets a page index, from the alignment at words:

- An aligned token takes the page of its galley token.
- An unaligned token of a note or a margin note takes the page of the
  nearest aligned token of the same note, before or after it. A note
  with no aligned token takes the page of its note reference. Gutenberg
  moves notes to the end of the book, so the page anchors around them
  say nothing of where they were printed.
- An unaligned token of the body, in a book with page anchors, takes the
  page of the body's anchor before it. An anchor's page is its printed page
  number plus its offset: the median of page index minus printed page
  number over the aligned tokens between this anchor and the next,
  which is constant over runs of pages (section 2).
- An unaligned token of the body in a book without anchors takes the
  page of the nearest aligned token before it.
- A token before every anchor and aligned token takes the page of the
  first aligned token after it.

A token whose page cannot be known is **unplaced**, listed apart and not
scored: an unaligned body token between two anchors whose pages have a
page of `exclude_pages` between them. It may have been printed on the
excluded page, as Stubbs' map captions were, between the anchors of
printed pages 34 and 35.

An anchor whose offset differs from both its neighbours' is an
`anchor_mismatch`: it says more about the alignment than about galley.
The scorecard counts them, and `summary.md` lists them.

A difference on a page in `exclude_pages` or `not_in_reference` is
listed apart and not scored.

### Differences

Each reference token, and each galley token, ends in one of these states:

| state | what it is |
|---|---|
| `matched` | aligned to a token with the same text |
| `changed` | aligned to a token with the same alignment key and another text, or paired in a replaced stretch |
| `split` | one reference token whose key equals the joined keys of two or more consecutive galley tokens: "replicate" against "repli-" "cate" |
| `glued` | two or more consecutive reference tokens whose joined keys equal the key of one galley token: "pamphlets published on" against "pamphletspublishedon" |
| `missing` | a reference token with no galley token |
| `extra` | a galley token with no reference token |

A replaced stretch is walked in order on both sides at once. At each
step, a `split` or a `glued` is tried at the current position of each
side, joining consecutive tokens with non-empty keys for as long as
their joined keys are a beginning of the other side's key, up to 12
tokens. The text layer glues long runs: Haskins page index 28 has
"Thelandisnotthewholeofnature'sgifttoNormandy;", eleven words, and with a
limit of 4 such runs were reported as `missing` words, 576 of Haskins'
1,606 (a third), although the words are in galley's output; else the two current tokens are
paired as `changed` when they are alike; else the one with the lower
position, relative to its side's stretch, is `missing` or `extra`. Two
tokens are alike when the similarity of their keys, as
`difflib.SequenceMatcher` measures it over characters, is at least 0.5,
or when both keys are empty. A token with an empty key is never alike
one with a non-empty key. What is left over at the end is `missing` or
`extra`. Pairing every token of a stretch in order, as the first build
did, paired 10,175 of Mariéjol's 21,769 changed pairs with a word of
nothing alike, such as "son" with "'", where the truth is a missing
word and an extra one; and it took the running heads out of the extras.
The 0.5 is a guess, to be checked on the baseline. The galley tokens of
a split, "repli-" and "cate", and the reference tokens of a glued, have
that state too.

A `changed` pair has a subkind, the first that applies:

| subkind | when | counted as an error |
|---|---|---|
| `convention` | equal once quotes, dashes and ligatures are written one way: `’` `‘` as `'`, `“ ”` as `"`, `–` `—` as `--` but `–` between digits as `-`, `ﬁ` as `fi` | no |
| `case` | equal but for letter case | yes |
| `punctuation` | equal once everything but letters and digits is dropped and case is ignored, accents kept: "Serfs." and "serfs" | yes |
| `diacritic` | equal alignment keys, and the accents differ | yes |
| `letters` | anything else | yes |

A difference on a token tagged as a marked correction has the subkind
`reference_correction` and is counted apart from the errors. Unmarked
corrections, such as Haskins' hyphenation made consistent, cannot be told
apart and count as errors.

### The stage a difference belongs to

A reference token has a state at each of the four stage outputs. Its
difference is attributed to the **first stage of the last run of
non-matched states**: the earliest stage from which it is never matched
again. A token not matched at markdown is an error of the book; its
difference is written to `differences.jsonl` once, with that stage.

A reference token that is not matched at some stage and matched at
markdown is **repaired** by the stage where it becomes matched. It is
counted in that stage's `repaired` score and not written as a
difference.

An extra galley token has no reference token to follow. The extra tokens
of each output are taken as a multiset of (page index, text). An extra at
markdown is attributed to the first output from which it is in that
multiset at every later output.

The running head and page number "THE NORMANS IN THE SOUTH 199", the
first line of Haskins' page index 214, followed through a galley that
does not yet remove running heads:

| output | state of its six tokens |
|---|---|
| words | `extra`, flagged `edge_of_page` |
| lines | `extra` |
| blocks | `extra`: structure did not remove it |
| markdown | `extra` |

The six extras are attributed to words, the first output of an
unbroken run to markdown, and written to `differences.jsonl` with stage
words and `edge_of_page`. Separately, `summary.md` groups the
differences by the work they call for: extras on the edge of the page,
and splits whose first galley token ends with "-", under structure's,
which removes such lines and joins such words; glued tokens under
extract's, which reads the spaces between words; the other differences
of words under analyze's and extract's, which read the text; and each
later stage's own differences under that stage. Once structure removes running heads, they are extra at words and
lines only, and do not reach markdown: no difference is written.

A word split by a hyphen at a line end, "repli-" "cate", which
structure joins into "replicate":

| output | state of the reference token "replicate" |
|---|---|
| words | `split` |
| lines | `split` |
| blocks | `matched` |
| markdown | `matched` |

It is counted once in `repaired` for blocks and is not a difference. Had
markdown broken it again, it would be a difference attributed to
markdown.

## 6. Scores

The scores are computed for each of the four outputs and written to the
scorecard. Each is given for every part apart: the body, the notes, the
index, tables, and figure captions. The index and tables are apart
because a scrambled text layer there (section 2) would otherwise drown
the body's score.

A reference token has the part of its block. An extra galley token has
the part of its page: the part that holds most of the reference tokens
of that page.

### Text

- `matched`, `missing`, `extra`, `changed` by subkind, `split`, `glued`,
  `reference_correction`, `unplaced`: counts of tokens. A split or glued
  difference counts the reference's tokens: 1 for "repli-" "cate", 3 for
  "pamphletspublishedon".
- `not_scored`: the reference tokens on pages of `exclude_pages` or
  `not_in_reference`; and `galley_tokens`, the tokens of the stage
  output. With them, the states, `unplaced` and `not_scored` add up to
  the reference's tokens, and the galley side to `galley_tokens`.
- `token_error_rate`: missing, extra, changed without `convention` and
  `reference_correction`, split and glued, divided by the reference's
  tokens. Lower is better.
- `edge_of_page_extra`: the extra tokens flagged `edge_of_page`.
- `repaired`, at lines, blocks and markdown: the reference tokens that
  the stage repaired.

### Structure

These are scored at blocks and markdown.

- **Paragraph boundaries.** A boundary is the gap between the last token
  of a body block and the first token of the next. galley's boundaries
  are mapped onto the gaps between the reference's tokens through the
  alignment. A galley boundary is right when it falls in the same gap as
  a reference boundary. Precision is the share of galley's boundaries
  that are right; recall is the share of the reference's that galley
  has. A galley boundary at a page break where the reference's paragraph
  runs on is a wrong boundary.
- **Block kinds.** For each reference block, the kind of the galley block
  that holds most of its aligned tokens. The scorecard gives the count of
  each pair, reference kind against galley kind.
- **Notes.** Each reference note is:
  - `as_note`: at least half of its aligned tokens are in one galley
    note;
  - `in_body`: at least half are in body blocks;
  - otherwise `missing`.

  For a note found `as_note`, its reference is right when galley's note
  reference for that note, mapped onto the gaps between the reference's
  tokens through the alignment, is within 3 tokens of the gap where
  Gutenberg's reference is.
- **Margin notes.** Each reference margin note is `as_margin_note`,
  `in_body` or `missing`, by the same rule. Its position is right when
  galley's margin note comes just before the block that holds the first
  token of the paragraph it precedes in the reference. Position is not
  scored in a book with `margin_notes_moved`.

The half and the 3 tokens are guesses, to be set again once structure
finds notes.

## 7. What the tool writes

For a book named `domesday`, under `runs/evaluation/domesday/` (ignored
by git):

```
book.toml                    written by the tool from books.toml
pages.json … book.md         galley's files (architecture §5)
evaluation/
  scorecard.json             the scores of section 6, per stage output and part
  differences.jsonl          one difference per line
  pages.tsv                  the table of section 8
  summary.md                 the scorecard, and the commonest differences by stage and kind
```

`runs/evaluation/summary.md` puts the books side by side, one row per
book and score; a book whose last comparison failed is shown as failed,
not with its earlier scores. Each `scorecard.json` holds the commit of
galley that made the book's files, which `run` records in the book
folder and `compare` reads from there, the commit of the comparison,
the date, the reference's ebook number and the tool's version. A book's
files are written to temporary files and moved into place, so that a
run cut short leaves the earlier files whole. A plan's work
report quotes the scores before and after its work.

Each line of `differences.jsonl` is one difference:

- `stage`, the stage it is attributed to; `state` and `subkind`, at
  markdown, which is the error of the book; `state_at_stage` and
  `subkind_at_stage`, at the attributed stage; and `part`;
- `page_index`, and `printed_page` where an anchor gives it;
- `reference`: the reference's tokens;
- `galley`: galley's tokens at markdown;
- `context`: up to 8 tokens before and after (a choice, enough to find
  the place in the book): the reference's of the same stream, or, for an
  extra, galley's of its page;
- `block_id` and `note_id` where galley's side has them;
- `edge_of_page`.

## 8. Finding pages with bad OCR

`pages.tsv` has one row per page, so that statistics that need no
reference can be tested against measures that do. The analyze stage
needs such a statistic to decide when to OCR a page again (architecture
§7b). Two kinds of bad OCR are in the four books, and a statistic has to
see both: letters misread inside words (Mariéjol) and a page scrambled
into single letters (Stubbs' index).

Measured against the reference, at words, without the tokens flagged
`edge_of_page`:

- `ocr_recall`: the share of the page's reference tokens that are
  `matched`, `split`, or `changed` with subkind `convention`, `case` or
  `punctuation`. It falls when words are misread or lost. A split, such
  as a hyphen at a line end, is a word read right (Haskins' words hold
  1,886 hyphens).
- `ocr_precision`: the share of the page's galley tokens that are aligned
  to a reference token with the same alignment key, or are part of a
  `split`. It falls when the
  page is scrambled: many galley tokens, few of them words of the
  reference.

Computed from galley's words alone, the candidates:

- `wordlist_share`: the share of the page's alphabetic tokens that are in
  galley's word list for the book's language. A token is lowered and
  stripped of punctuation at both ends; it is alphabetic when what is
  left is letters only.
- `single_letter_share`: the share of tokens that are one letter once
  stripped, other than the words of one letter of the book's language
  (English `a`, `i`, `o`; French `a`, `à`, `y`).
- `inner_symbol_share`: the share of tokens with a character that is
  neither a letter nor a hyphen between two letters, as `t*e`.
- `ocr_confidence_mean`: the mean of Tesseract's confidences, on pages
  galley read with OCR; empty otherwise.

And, for context: `page_index`, `printed_page`, `text_source`, `part`,
and the page's token count.

The tool computes the columns. Which statistic galley uses, and its
threshold, is decided in analyze's spec from this table.

A first look, measured another way: against the plain-text edition,
with a key that kept accents, and with the galley-side share, close to
`ocr_precision`. The word list was rebuilt by hand the way the owner's
earlier OCR experiments (`ocr_lab`) built it, from Tesseract's language
data, since galley's `wordlist.py` does not exist yet. Pages with 50
tokens or more:

| book | pages | Spearman correlation of `wordlist_share` with the galley-side share |
|---|---|---|
| Mariéjol | 440 | 0.87 |
| Haskins | 260 | 0.66 |
| Stubbs | 320 | 0.46 |
| Domesday | 537 | 0.40 |

The share of dictionary words followed the quality of Mariéjol's text
layer, which misreads letters. It missed the scrambled pages: Stubbs'
index pages scored 0.90–0.99 in the word list, and 0.02–0.27 of their
galley tokens were words of the reference. Tokens of one letter, once
stripped and lowered, are 9.7% of Stubbs' tokens, 6.4% of Domesday's,
7.5% of Mariéjol's and 2.1% of Haskins'; in Haskins nearly all are the
words "a" and "I" (0.1% without them). This is why
`single_letter_share` is a column, and why it leaves out the words of
one letter. Every number of this table is measured again by the tool's
first run, on its own definitions, before analyze's spec uses it.

galley's `wordlist.py` is built first, as architecture §12 gives it,
because the tool and analyze both need it.

## 9. How it is run

The tool is a second package of the repository, in `tools/galley-eval/`,
a member of a uv workspace with galley. It has its own `pyproject.toml`
and command, `galley-eval`, and depends on galley; galley's wheel holds
nothing of it. The root `pyproject.toml` declares the workspace, has the
tool in its development dependencies, so that `uv run galley-eval` works
from the root, and adds `tools/galley-eval/tests` to pytest's
`testpaths`, so that `uv run pytest` runs the tool's tests with galley's. It uses only galley's public modules: `galley.model` and
`galley.book_folder`, to read galley's files; `galley.fidelity.read_markdown`,
to read `book.md`; `galley.config`, for the language codes; and
`galley.wordlist`.

```
galley-eval run [<name> ...]       run galley on each book, then compare; all books when none is named
galley-eval compare [<name> ...]   compare the files already in the book folders
galley-eval summary                rewrite runs/evaluation/summary.md from the scorecards
```

`run` writes each book's `book.toml` from `books.toml` and runs
`galley2epub run` on the book folder as a separate process, so that the
command itself is what is tested. A stage that fails is reported for
that book with its error, and the other books go on. The four books take
about 40 s of galley (section 2). The first build compared a book in
3.0 s (Haskins) to 13.5 s (Mariéjol), of which about 4 s for Domesday is
reading galley's JSON; the alignment keys of the reference are computed
once per book, not once per output. Books are compared one after
another.

The function the tests call:

```python
def evaluate(book: EvaluationBook, folder: BookFolder, reference_html: Path) -> Evaluation:
    """Compare galley's files in `folder` with the reference; write nothing."""
```

`EvaluationBook` is one entry of `books.toml`. `Evaluation` holds the
scorecard, the differences and the page table, as frozen values; writing
them is a separate function.

## 10. How it is verified

- **Unit tests**, on literal inputs:
  - the reader on small pieces of HTML, one per rule of section 4: a
    page anchor inside a word, a note label that must go, a margin note
    with `<br>`, a `p` inside a margin note, a Mariéjol back link that is
    not a note reference, a marked correction;
  - the alignment and the states on short token lists written for each
    state and subkind of section 5;
  - the attribution to stages on tokens whose states are given at the
    four outputs, including the two examples of section 5;
  - the boundary, note and margin-note scores on hand-made blocks.
- **An excerpt test.** A new excerpt, `haskins_eval`, cut by
  `scripts/fetch_samples.py`: about ten PDF pages of Haskins with
  footnotes, a chapter start and an index page. With it go:
  - the part of Gutenberg's HTML for the same pages, under
    `tests/fixtures/evaluation/`, with the licence removed (the text is
    in the public domain; Gutenberg's name and licence are not);
  - galley's output files for the excerpt, made once and committed
    beside it, so that the test does not change each time galley
    improves;
  - the excerpt's entry, as in `books.toml`, whose page indices are
    those of the excerpt PDF.

  The test runs `evaluate` on them and checks a few differences, each
  stated in the test by its page, tokens, state and stage: a running
  head, a hyphen at a line end, a footnote left in the body. Whoever
  writes the test chooses them from the pages and writes them down; the
  owner checks them by eye against the page images before the test is
  committed.
- **The reading rules of each book**, marked `whole_book` because they
  need the downloaded HTML: the reader finds each book's
  `expected_counts`, such as Domesday's 1,729 notes and 593 margin notes.
- **The whole set** is not a test. It is run by hand with `galley-eval
  run` at the end of a plan, because its numbers are what is measured,
  not something to pass or fail.

## 11. Open points

None. The choices that were the owner's were taken in chat on 15
November 2026 and are listed in the opening.

## 12. Not in this spec

- **The statistic that detects bad OCR, and its threshold**: analyze's
  spec, from the table of section 8.
- **What galley does with quotes, dashes and ligatures**: the markdown
  stage's spec. Here they are counted apart as `convention`.
- **How the differences are sorted into bugs and new features, and who
  does it**: the plans that use the tool. A plan runs the tool before and
  after its work, and its work report gives both scorecards.
- **Synthetic books**, a known text typeset into a PDF, where every
  structure error is galley's: later, if the evaluation set leaves a
  kind of error unmeasured.
- **Comparing the EPUB**: as with the fidelity check, the comparison
  stops at `book.md` (architecture §13).
