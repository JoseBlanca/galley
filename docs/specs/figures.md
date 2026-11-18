# Figures inside text pages: finding, cutting and placing them

A figure printed inside a text page, a drawing, a map or an engraving
with text above or below it, is lost today: galley cuts pictures only
from plates, pages that are mostly a picture (`docs/specs/plates.md`).
On a text page the picture is dropped, the words the OCR read in it run
into the paragraphs, and its caption is read as part of a paragraph.
The owner, reading the EPUB of Haynes' book, asked on 18 November 2026
to keep "these simple figures". This spec says how analyze finds such a
figure, how extract cuts its picture, how layout keeps the words read
inside the picture apart, and how structure removes those words, keeps
the caption as the figure block's text and places the block where the
picture was printed. The EPUB then shows the picture with its caption
between the paragraphs, as it shows a plate.

**What a reader of the EPUB will see.** In Haynes' book, each of its 25
figures as a picture, with its caption ("figure 2." and the picture's title) under
it as a caption, and the paragraph the figure interrupted read whole
before it. In Turney's insert of illustrations, 14 pictures, 11 with
their numbered captions; on page 174 the two magazine covers as two
pictures sharing the caption "14 (a)… (b)…", and no heading made of the
cover's lettering; on page 175 the two pictures with their captions,
but the newspaper's masthead and headline, printed above its photograph,
still as text and a heading unless the owner marks them in the config
(section 8). In Kadesh, its 6 maps with their captions, and 11 of its
quotations printed in hieroglyphs or Arabic as pictures (section 11,
open point 1, settled).

galley runs as stages, each writing one file for the next: **analyze**
says what each page is (`pages.json`), **extract** reads each page's
words from the PDF's **text layer**, the words the scanner's OCR put
behind the page image (`words.json`), and cuts the pictures into
`images/`; **layout** groups the words into **regions** (a column of
text, a margin, the running head at the top of the page, which is the
page's **head line**) and lines (`lines.json`); **structure** makes the
**blocks** of the book, paragraphs, headings, figures (`blocks.json`);
markdown and epub write the book. The **body stream** is the page's
running text, the lines structure groups into paragraphs; **side text**
is what it places beside them (margin notes, figures). A word a stage
takes out of the book is a **removal**, recorded in its file with the
page, the box, the text and a **reason** (architecture §8).

Dated 18 November 2026. No code exists for it. It builds on
`docs/architecture.md` (cited as "architecture §n"), `docs/glossary.md`,
`docs/specs/plates.md` (plates §n), `docs/specs/layout.md` (layout §n)
and `docs/specs/structure.md` (structure §n). It changes four formats:
pages.json gains the figures' boxes, words.json and lines.json a kind
for each figure, and blocks.json a removal reason, in the version 5
that structure §29 to §33 (lists and the printed contents) also make
(section 7; its wording is applied to the architecture and the
glossary). markdown and epub already write a figure block, with its
image and caption (architecture §9), and do not change.

The numbers were measured on 18 November 2026 with pypdfium2 on an
Apple M5 Pro, on every text page of eight books: the six public-domain
books of `samples/public_domain/`, named as `docs/specs/plates.md` names them (**Kadesh**,
**Gierke**, **Haskins**, **Stubbs**, **Domesday**, **Mariéjol**), and
the owner's two books in `samples/`, R. D. Haynes' book (**Haynes**), and J. Turney's book
(**Turney**), which are under copyright: this spec names their cases in
a few words and no test cuts them. The words are those of the runs of
the plan owner-books, `runs/owner-books/<book>/words.json`, which are
`text_layer.layer_words` without the config's excluded regions. Page
means page index, from 0, in the whole book.

## 1. Terms

- **Figure**: a picture of the book cut into `images/` (glossary). A
  **plate** is a page that is mostly one; an **in-page figure**, the
  subject of this spec, is one printed on a text page among its lines.
- **Square**, **ink**, **inked square**, **picture square**: as plates
  §2 defines them, here with squares of 12 pt a side, 6 by 6 pixels at
  36 dpi: a pixel is ink when it is darker than the page's median gray
  (the gray of half the page's pixels or more, its paper) by more than
  25 levels of 255; a square is inked when at least 6% of its pixels
  are ink, 3 of its 36; a picture
  square is an inked square that no word box, grown by 2 pt on every
  side, touches.
- **Group**: a set of picture squares that touch side by side, not
  only by a corner, as plates §2's largest group, but every group of
  the page, not only the largest.
- **Known word**: a word that `wordlist.is_known_word` takes (plates
  §2): one of at least two letters found in the word list of the book's
  language, or a number.
- **Numeral**: 1 to 6 characters, each a digit or one of the letters
  i, v, x, l, c in either case, with or without a "." or "," after
  them: the OCR reads 1 as "i", "l" or "I" ("figure li." for 11,
  Turney's "2i." for 21), and roman numerals are common ("MAP 111." for
  III).
- **Caption label**: the words that open a caption, one of:
  - "figure", "fig.", "fig", "plate" or "map", in any case, as the
    line's first or second word, followed by a numeral ("figure 2.",
    "FIGURE l6.", "MAP vi."; second, because the OCR may put a mark of
    the picture first, Haynes 310's "M FIGURE 25.");
  - a numeral of at most 3 characters ending in ".", followed by a word
    of a capital letter and then a small one ("13. The", "i. The",
    "4. Eighteenth-century"), or a numeral of at most 3 characters
    followed by a word in brackets ("14 (a)", "2. (top)"). Turney
    numbers its captions so. The capital keeps out Kadesh's numbers of
    inscriptions beside its maps, "8.", "12. n lie" and "L. P. H.,"
    (measured: with any numeral followed by a word, 4 such lines became
    captions of Kadesh's maps 36, 38 and 45; with this rule, none).
  The label is looked for at the start of a run of words, not only of
  a line, because layout may put a caption's words in one line with
  other text (section 5).
- **Figure text**: the words the OCR read inside an in-page figure's
  picture: its lettering, its labels and the marks of its shading. The
  picture's image shows them, so structure removes them, with a record
  (section 5).

## 2. What the books show

| book | in-page figures | what they are | today |
|---|---|---|---|
| Haynes | 25, one each on pages 15, 25, 34, 45, 53, 58, 64, 71, 84, 95, 97, 111, 114, 119, 124, 133, 142, 143, 145, 162, 180, 182, 253, 254, 310 | engravings, paintings and photographs, numbered "figure 1" to "figure 25", each with its caption below the picture or in a narrow column beside it | the picture is lost and the caption runs into a paragraph: on page 25, figure 2's caption sits inside the paragraph that runs from page 24 to 25 (`runs/owner-books/haynes/book.md`, line 139, outside git) |
| Turney | 14 on 12 pages: 164, 166, 167, 169, 172 to 176, 179, and the back cover, 311 | the book's insert of illustrations, pages 164 to 179, each page one or two pictures with numbered captions ("13. The…") and no running text; 170, 177 and 178 of the insert are plates, and 165, 168 and 171 are excluded by the config | 174 and 175, the reproduced magazine covers and newspaper front pages (figures 14 to 16), are text pages because their captions and the newspapers' lettering hold more than 20 known words, the plate rule's limit (plates §2): the lettering "Inside: Crisis in Portugal" becomes a heading, and so does the Daily Mail's headline |
| Kadesh | 6 maps on pages 29, 33, 36, 38, 41 and 45; blocks of hieroglyphs on 27, 32, 37, 39, 40, 44, 50 to 53, and of Arabic on 20 and 21 | the maps "MAP III." to "MAP VIII.", three of them narrow, with the text set beside them (36, 38, 41); the blocks, each a numbered quotation of an inscription | the maps' labels ("Kadesh", "Orontes") and the hieroglyphs' junk ("AAAAAA", "\\(t=]") run into the paragraphs; the pictures are lost |
| the other five | none | Domesday's tables (page 425, "TABLE I.") are text with a text layer, not pictures | |

The rule of section 3 finds every figure of this table, 56 in all:
Haynes' 25, Turney's 14 and Kadesh's 17, its 6 maps and 11 groups of
hieroglyphs or Arabic (on pages 20, 27 (two), 37, 40, 44 (two), 50,
51, 52 and 53). It leaves out Kadesh's smaller groups of hieroglyphs or
Arabic, from 43 to 115 squares (pages 21, 32 and 39 among them),
against a threshold of 120, and finds nothing else on the text pages of
the eight books.

## 3. analyze: finding an in-page figure

analyze already renders every page it tests for a plate at 36 dpi
(plates §2) and has its text layer's words. On each page that ends as a
`text` page it looks again at the same render, with smaller squares, for
groups of picture squares; nothing more is rendered.

1. The render is cut into squares of 12 pt (6 pixels at 36 dpi) from
   the top left. An outer band of 24 pt, two squares, is left out, and
   a partial square at the right or the foot. A word inside one of the
   page's `exclude_regions`, by the test extract uses (the middle of
   its box inside the region), does not stop a picture square: an
   excluded region is not text (section 8, Turney 175).
2. The page's groups are found, and each group's **box**: the smallest
   box that holds every ink pixel of its squares, in points, tighter
   than the squares, so that the line of text above or below it is
   outside. Where a group's square touches the outer band side by side,
   the ink pixels of the two band squares beyond it, in its row or
   column, count for the box too, so that a picture printed to the
   edge of the scan is cut whole: without this, 12 of Haynes' 25 boxes
   stop at the band, 24 pt from the left edge, and Haynes 53's picture
   loses 23 pt on its right, Turney 166's 9 and 19 pt on its sides
   (spec review, 18 November 2026). They never count as squares of the
   group. The box can then take in a strip of the scan's dark edge,
   24 pt at most.
3. A group is a **figure** when both hold:
   - it has at least **120 squares**;
   - at most **12 known words** have the middle of their box inside the
     group's box (the box before it is grown into the band).

pages.json gives each `text` page its figures' boxes, from the top down
and, at the same top, from the left (section 7). A page of any other
kind has none: a plate is a figure whole (plates §3), and a page before
the front-matter end is dropped.

**Measured**, on the text pages of the eight books, with the words of
words.json:

| groups | squares | known words in the box |
|---|---|---|
| the figures of section 2: Haynes' 25 | 228 (page 15) to 1,145 | 0, but 7 on page 53 (the engraving's lettering) and 1 on 310 |
| Turney's 14 | 299 to 1,233 | 0, but 5 on 174 ("Inside: Crisis in Portugal") and 1 on 164 and 176 |
| Kadesh's maps | 132 (page 38) to 554 | 0 to 3 |
| Kadesh's blocks of hieroglyphs and Arabic | 43 to 371 | 0 to 6 |
| Mariéjol's text pages whose OCR failed (57, 121, 169, 265, 347, 410, 421) | 57: 498, 265: 634; the others 62 to 113 | 57: 52, 265: 29; the others 10 (169) or more |
| Kadesh 74, the library's card pocket on the last page | 130 | 17 |
| Domesday 553, a library stamp at the top of the page | 100 | 0 |
| Mariéjol 92, a running head printed as a picture, the layer holding no word of it | 68 | 0 |
| Kadesh's rules under the running heads | fewer than 40 | |

| threshold | value | from |
|---|---|---|
| render | 36 dpi, the plate rule's | decided: no second render |
| square | 12 pt | measured: with plates' 24 pt squares, Kadesh 36's map and the line of hieroglyphs beside it were one group of 64 squares whose box, 384 pt wide, held 138 words of the text set beside the map; at 12 pt they are 144 and 85 squares apart. At 72 dpi with 12 pt squares the counts differ by at most 35 (Kadesh 41's map: 148 against 183) and no figure changes |
| outer band | 24 pt | measured: with 12 pt, the dark edges of the scan made groups on 7 pages (Mariéjol 181, 375, 381, 429, 452; Domesday 427; Stubbs 248) |
| ink, inked square, word box grown | 25 levels, 6%, 2 pt | plates §2's, for pages with a text layer |
| group | at least 120 squares | measured: the smallest figure is Kadesh 38's map, 132; the largest group that is not a picture and has few known words is Domesday 553's stamp, 100 |
| known words in the box | at most 12 | measured: the figures hold 7 or fewer (Haynes 53); of the groups of 120 squares or more that are not pictures, Kadesh 74's card pocket holds 17 and Mariéjol 265 and 57 hold 29 and 52 |

The two thresholds leave margins of 12 squares below the smallest map
and 20 above the stamp, and of 5 known words above Haynes 53 and below
Kadesh 74. A figure the rule misses, or a page
it takes wrongly, is listed in the logs (below); the config's levers are
in section 8.

analyze logs at INFO, for each page with figures, their number and each
box with its squares and known words, so that the owner can find them.

**Cost.** The rule reuses the plate rule's render. Rendering Haynes'
436 pages at 36 dpi and finding the groups took 6.8 s on one thread
with 12 pt squares, against 6.7 s with the plate rule's 24 pt squares:
the smaller squares cost nothing that was measurable.

## 4. extract: cutting the picture

On a `text` page with figure boxes, extract has the PDFium thread render
the page at 300 dpi and cuts each box out of the render, the box's
sides rounded outwards to whole pixels, as an 8-bit grayscale PNG,
`images/figure-<page index, 4 digits>-<n>.png`, n from 1 in the order of
pages.json. The page's `PageWords.figures` holds one `Figure(box, image,
dpi=300, kind=FigureKind.IN_PAGE)` for each, in that order. The page's words are read as on any
text page; none is removed here. A Haynes figure, about 390 by 290 pt,
is about 1,600 by 1,200 pixels; its file size was not measured (a whole
plate page of Kadesh is 2.36 MB, plates §3).

The file name differs from a plate's, `plate-<page index>.png`, because
a page may have two in-page figures (Turney 174, 175 and 176).

## 5. layout and structure: the figure's words, its caption, its place

### Which figures are in-page

extract writes each `Figure` with its **kind**, a new field: `plate`
for a plate's (plates §3) and `in_page` for one cut by section 4, and
layout copies it to lines.json (section 11, open point 2, settled: it
changes words.json and lines.json). layout and structure need it because lines.json has no
page kind: structure today sends every page that has a figure to the
plate rules of structure §18 (`src/galley/structure/__init__.py`, where
`page.figures` is tested), which make the whole page a caption and stray
words and refuse a page with two figures. With the kind, structure §18
runs on a page whose figure is a plate's, and the rules below on the
in-page figures of a text page.

### layout: the figure's words kept apart

A word of the text layer printed inside a picture lies on the same rows
as the text beside it: Kadesh's map labels beside the lines set to the
right of the map, Turney's caption beside a cover. Grouped with them,
it joins their lines, and structure cannot take it back out. So layout,
on a page with in-page figures, first lays the page out with all its
words, as today (layout §3, "Per page", steps 1 to the end, and the
re-reading), and then takes out of its regions' lines the words whose
middle lies inside an in-page figure's box, but for the words of the
page's first row (the row with the smallest top, as layout §1 makes
rows), which may be the head line and stay where they are. A line left
with no word is dropped, and so is a region left with no line; a line
or region that lost a word has again the smallest box that holds what
is left. The words taken out make one region per figure, after the
page's other regions, whose box is the figure's box exactly, its lines
grouped as layout groups any region's; a figure with no such word has
no region. The page's other regions are then those it has today, less
the figure's words. The words are taken out after the layout, not
before it, because the bands and columns are found on all the page's
rows: taken out before step 1, as a draft of this section did, the
hieroglyphs among the footnotes of Kadesh page 52 left gaps that turned
its 7 footnotes into 4, three of them into quotations of the body, and
whole Kadesh had 148 footnotes against 152 (review, 18 November 2026).

A figure's region is never re-read with Tesseract
(`docs/specs/reocr.md`): no region read again replaces a word of the
text layer whose middle lies inside an in-page figure's box, and of
Tesseract's words, those whose middle lies inside one are dropped
before the reading is scored. A footnote band's crop runs across the
page's width, and on Kadesh page 51 it crosses the hieroglyphs: without
this, Tesseract's reading of them would enter the notes, a second copy
of words the figure's region holds.

### structure: removing the figure text

A region of a page whose box equals one of the page's in-page figure
boxes is that figure's region. It takes no part in structure's survey
of the book (structure §2: body measures, running heads, the kinds of
regions) nor in finding the page's body column and margins: a region
as wide as a picture would otherwise count as the page's widest. Its
lines are removed as `figure_text`, one removal per line, as
`plate_text` is (structure §18, rule 2), but for those that open or
continue a caption (below). So is the page's head line when the middle
of each of its words lies inside an in-page figure's box and structure
§3 makes it neither a running head nor a page number: Turney 174's
"Inside: Crisis in Portugal", the lettering at the top of the first
cover, is the first row of a page without running heads.

All of them, legible or not, go: the picture's image shows them, and a
map's labels or a newspaper's headline read as a sentence are not text
of the book. This differs from a plate, where a row of known words is
kept as caption (structure §18): a plate's whole page is its picture,
and its caption is printed inside it.

### structure: the caption

A figure's **caption** is found among the page's lines, in the figure's
region or outside it, before the body lines are grouped into
paragraphs. It works on **rows**, those of structure §18, rule 3: by
top, then left side, a line joins a row when its vertical centre lies
within the top and bottom of the row's first line. Rows, not lines,
because layout may cut a caption's line: on Turney 175 and 176 it makes
"16. The" and "17." lines of their own, apart from the rest of their
line.

1. **The label row.** A row in which a run of words, from its first word
   or from a later one, opens with a caption label (section 1), and
   which lies next to the figure in one of three ways:
   - **below**: the row's top from 6 pt above the figure's bottom to 24
     pt below it, and the middle of the label's first word between the
     figure's left and right sides, each moved 6 pt outwards;
   - **above**: the row's bottom from 24 pt above the figure's top to
     6 pt below it, and the same test of the label's first word;
   - **beside**: the row's top between the figure's top and bottom, and
     either the label's first word's left side 0 to 30 pt right of the
     figure's right side (a caption on the right), or every word of the
     row left of the figure and its last word's right side 0 to 30 pt
     left of the figure's left side (a caption on the left).
2. **The words of the label row.** Below or above, the words whose
   middle lies between the figure's sides, each moved 6 pt outwards;
   on the right, the words whose middle lies right of the figure's
   right side; on the left, those left of its left side. The other
   words of the row stay in their lines: on Kadesh 38, layout makes one
   line of the map's "MAP vi. Third Positions" and of the line of text
   set beside the map, "Shabtuna and the…", which starts 12 pt right of
   the map.
3. **The rows after it.** Each next row, from the top down, while all
   three hold: its top is at most 20 pt below the top of the caption's
   previous row; it opens with no caption label; and it lies on the
   caption's side: below or above, it lies between the figure's sides
   each moved 12 pt outwards, or its left side is within 3 pt of the
   label row's (Haynes' captions are set to the width of the text
   column, which is wider than some of its pictures); on the right or
   left, it lies wholly on that side of the figure. A row is taken
   whole.

Several label rows next to one figure give one caption, in the order of
their tops. A figure with no label row next to it has no caption. A
label row next to two figures goes to the one whose box is nearer to
the row's box.

**Measured** on 18 November 2026 on the rows of the lines of
`runs/owner-books/<book>/lines.json`, the words inside the figures'
boxes taken out of them as layout will: each of Haynes' 25 figures has
a caption, 12 below it (5.4 to 8.1 pt below) and 13 on its right (10.4
to 17.3 pt), of 1 to 13 rows, ending at the caption's last word; 11 of
Turney's 14 (5.3 to 14.7 pt below, 6.5 to 20.0 pt beside), of 2 to 12
rows, two of them short of their last row, which layout put in one line
with words of the picture next to it (175, figure 15; 176, figure 17);
each of Kadesh's 6 maps (3.5 pt above its bottom to 11.7 pt below), one
row each, with no word of the text beside or under the map. The 3 of
Turney without a caption are the second cover of page 174, whose
caption "14 (a)… (b)…", printed beside the first cover, names both and
goes to the first; the film still of 167, whose printed lettering
stands between it and its caption (section 8); and the back cover.
Kadesh's groups of hieroglyphs have none. Within a caption the rows
follow each other at 10.9 to 14.7 pt; after a Haynes caption the next
row is 23.6 to 51.5 pt below its last. With 12 pt instead of 6 in rules
1 and 2, "at" and "of" of the text set beside Kadesh's maps 33 and 41
joined their captions; with rule 3 limited to the 20 pt alone, the body
line under Kadesh 29's caption and the footnotes under 33's and 41's
joined theirs (found by the spec review); with the figure's sides alone
in rule 3, Haynes 119's caption stopped after 4 of its 7 rows.

The caption rows, from the top down and each from the left, are the
text of the figure block; their hyphens are joined as in any block, and
their words are not searched for note references. They are taken out of
the body stream, so they never reach a paragraph.

The caption is found in structure's step 2.2 (structure §2), after the
running heads are removed and before the heading lines (step 2.3), the
list items and the contents entries (step 3.1) are found. So a caption
row is never a heading, a list item or a contents entry, although a
Turney caption "13. The…" has the form of a numbered list's marker
line. A row that opens with a caption label and lies next to no figure
stays in the body stream, and the rules of structure see it as any
line: Turney 166's captions of the facing page (section 8) are tested
by the list rules (structure §29) as any line is. Whether one of them
starts a list was not measured; the whole-book count of Turney's list
items (structure §32: none) shows it.

### structure: where the figure block goes

A figure's **place** is between the body lines printed above it and
those below: the last line of the body stream, in reading order, whose
top lies above the figure's top, on its page or, when the page has none,
the last body line of the pages before. The figure block goes after the
paragraph that holds that line: when the figure is printed in the
middle of a paragraph, after the whole paragraph, never inside it. When
that line is in a list item (structure §29), the block goes after the
list's last item, as after a paragraph, so that the EPUB does not cut
the list in two; when it is in a contents entry (structure §30), after
the run's last entry. A list goes on across a figure printed between
two of its items (structure §29, rule 5). A
paragraph cut by the figure, its
lines above and below, is one paragraph, as across a page break: the
figure's lines and its caption are out of the body stream, so the
paragraph rules see one line follow the other, and a hyphen at the
line before the figure joins the word after it (structure §5). Haynes'
figure 2 is printed at the top of page 25, inside the paragraph that
runs from page 24 to page 25: its block comes after that paragraph. A
figure before any body line of the book goes first.

The figures of a page come in the order of pages.json. A page's figure
block comes before the side text that structure §6 places after the same
paragraph. Its `origin` is one entry, the box that holds the figure and
its caption lines; its id counts on its page as any block's
(architecture §7).

## 6. The public interface, and markdown and epub

`run` of each stage is unchanged in what it reads, deletes, checks and
writes. The pure parts, which the tests call on values made in the
test:

```python
# galley.analyze

def figure_boxes(page: RenderedPage, words: tuple[tuple[str, Box], ...],
                 excluded: tuple[Box, ...],
                 lower_case_words: frozenset[str]) -> tuple[Box, ...]: ...
    # The boxes of the in-page figures of a text page by section 3, in
    # points, from the top down and then from the left. `words` are the
    # text layer's words, each its text and box in points; a word whose
    # box lies inside one of `excluded`, the page's exclude_regions, does
    # not stop a picture square and is not counted.

# galley.structure

def is_caption_label(words: tuple[str, ...]) -> bool: ...
    # Whether the run of words `words`, left to right, opens with a
    # caption label (section 1).
```

markdown and epub are unchanged: a figure block is written as a plate's is, its image
with the caption under it (architecture §9; `src/galley/markdown`), and
the EPUB centres the image within the page (`src/galley/epub/style.css`).
The EPUB grows by each figure's image; making the images smaller is the
epub spec's work, as for plates.

## 7. The format changes, and the wording for the architecture

Four formats change, which other stages read; they were accepted for
the owner (section 11, open point 2). After them the owner reruns
analyze, which deletes every later file:

- **pages.json, version 3**: `PageInfo.figure_boxes: tuple[Box, ...]`,
  the boxes of the page's in-page figures in points, from the top down
  and then from the left; empty on a page that is not `text`.
- **words.json, version 3**, and **lines.json, version 4**:
  `Figure.kind: FigureKind`, `plate` or `in_page` (section 5).
- **blocks.json, version 5**: the removal reason `figure_text`. The
  revision of structure §29 to §33, written the same day, takes
  blocks.json to 5 too, with lists and contents entries; the two
  changes make one version 5, not two.

Reading a file of an earlier version is the error of architecture §8.
A region whose box is a figure's is a value lines.json already holds.

The wording below was applied to the architecture and the glossary on
18 November 2026, with the lists revision's; it is kept as the record
of what this spec changed there.

- §8, `PageInfo`: add "`figure_boxes: tuple[Box, ...]`: the boxes of the
  figures analyze finds inside a text page, in points, from the top down
  and then from the left; empty on any other page
  (`docs/specs/figures.md` §3)."
- §8, `Figure`, in place of "For now figures are cut from plate pages
  only, one per plate, and its box is the whole page; figures inside
  text pages are not detected yet.": "A plate page has one figure, whose
  box is the whole page (`docs/specs/plates.md`); a text page has one
  for each box of its `figure_boxes`, cut to that box
  (`docs/specs/figures.md`). `kind: FigureKind` says which: `plate` or
  `in_page`."
- §8, lines.json, after `Region`: "On a page with in-page figures, the
  words whose middle lies inside a figure's box, but for those of the
  page's first row, are taken out of the regions the page's layout made
  with them and are a region of their own whose box is the figure's
  box (`docs/specs/figures.md` §5)."
- §8, the versions: pages.json 3, words.json 3, lines.json 4, blocks.json
  5, with the sentence on what each change added.
- §8, `RemovalReason`: add "`figure_text` (the words the OCR read
  inside a figure printed on a text page: its lettering, labels and
  shading, which its image shows; `docs/specs/figures.md` §5)".
- §5, `images/`: "(plate-<page index, 4 digits>.png,
  figure-<page index, 4 digits>-<n>.png)".
- §9, analyze, after the sentence on plates: "On a text page it also
  finds the figures printed among the lines, from the same render, as
  groups of ink that no word covers (`docs/specs/figures.md`)." extract:
  "A figure inside a text page is cut from a render at 300 dpi to its
  box." layout: "It keeps the words read inside a figure in a region of
  their own." structure, after "removes its stray words": "removes the
  words read inside a figure on a text page, keeps its caption as the
  figure block's text, and places the block after the paragraph printed
  before it".
- The glossary: **caption**, add "On a text page, the lines next to an
  in-page figure that open with a caption label ("figure 2.", "MAP
  vi.")"; **figure**, add "An **in-page figure** is one printed on a
  text page among its lines"; and **figure text**, as section 1 gives
  it.

## 8. Cases

- **No caption**: a figure block with no spans, placed as any figure
  (Kadesh's groups of hieroglyphs).
- **Hieroglyph and Arabic blocks** (Kadesh): figures from 120 squares,
  so 11 groups become images and the smaller ones, 43 to 115 squares,
  stay as today, lost with their junk in the paragraphs (section 11,
  open point 1, settled).
- **Lettering outside the box** (Turney 175 and 167): words printed as
  part of a picture stop its picture squares, so lettering at its edge
  stays outside the group. The Daily Mail's masthead and headline lie
  above the photograph's group and stay text, the headline a heading;
  the film still's caption in capitals lies between the picture
  and its caption, which is then too far to be found and stays a
  paragraph. The owner names such lettering in `exclude_regions`
  (architecture §6): its words are then removed as `excluded_region` by
  extract and do not stop the picture squares, so the group and the
  image take it in. Not measured: the configs of Haynes and Turney are
  the owner's.
- **Captions of another page** (Turney 166 and 167): under "facing
  page", the captions of the pictures of the facing page, which has no
  text layer and is excluded, are next to no figure and stay paragraphs,
  as today.
- **Junk just outside the box**: a word of the picture whose middle lies
  outside the ink box stays text, as today (Kadesh 29's "it Am." at the
  foot of the map, Turney 164's ": in.- X;" at the engraving's left
  edge).
- **Two pictures in one group**, set closer than 12 pt: one figure and
  one image, with the captions of both. At 24 pt squares Turney 174's two
  covers were one group; at 12 pt they are two, and the eight books
  have no such group.
- **A figure across two pages**, or across a spread: each page's part is
  a figure of its own, with the caption where it is printed. The eight
  books have none.
- **Ornaments**: printer's flowers, headpieces, rules and a page number's
  dashes are not figures when they make fewer than 120 squares, the
  size of a picture about 144 by 120 pt with no white in it. Kadesh's
  rules under the running heads make 43 or fewer, Mariéjol's running
  head printed as a picture 68. A larger headpiece would be a figure
  without a caption; the eight books have none.
- **Tables** are not figures: their words cover them, and no table page
  of Domesday gives a group of more than 100 squares (Domesday 553, the
  largest, is a stamp). A table scanned without a text layer would be a
  figure, its picture kept.
- **A plate** is never searched for in-page figures, and a page with
  in-page figures is not a plate: the plate rule decides first
  (plates §2), unchanged.
- **A text page whose OCR failed** (Mariéjol 265): at least 29 known
  words in the group's box, not a figure. A failed page with 12 or fewer
  known words in a large group would be taken, and its words removed as
  `figure_text` with a record; the eight books have none.
- **A wrong figure**: the page goes into `exclude_pages`, or the region
  into `exclude_regions` when the cause is a stamp or a label. A config
  key to refuse a figure is not added until a book needs one.
- **The back cover** (Turney 311): a picture and the publisher's lines,
  a figure; such a page belongs in `exclude_pages`.

## 9. How it runs in parallel

As the plate rule: the 36 dpi render and the 300 dpi renders of extract
are made in the one PDFium thread (architecture §12), the groups are
found in the worker threads, and each page needs nothing from the
others. The output does not depend on the number of threads.

## 10. How it is verified

**Unit tests**, on values made in the test:

- `figure_boxes` on a `RenderedPage` of white, 300 by 450 pixels at 36
  dpi: a block of black of 12 by 12 squares (72 by 72 pixels) and no
  words is one figure whose box is the block's; 10 by 11 squares (110),
  none; a block of 20 by 20 squares with 13 known words of 1 by 1 pt
  inside it, none, and with 12, one; a word box across its middle that
  splits it into two groups of fewer than 120 squares each, none; a
  black band 2 pt wide along the top, inside the outer band and apart
  from the block, does not change the box; a block that runs into the
  outer band on its left, a box that reaches the block's left side; two blocks apart by one white square, two figures in
  order of their tops; a block whose squares are touched by an
  excluded region's word, one figure.
- `is_caption_label`: ("figure", "2."), ("FIGURE", "l6."),
  ("figure", "li."), ("MAP", "111."), ("MAP", "vi."), ("13.", "The"),
  ("14", "(a)"), ("2.", "(top)"), ("2i.", "The"), ("M", "FIGURE",
  "25.") are labels; ("figure", "drawn") (a line inside Turney 179's
  caption), ("Figure",), ("8.",), ("12.", "n", "lie"), ("L.", "P.",
  "H.,"), ("1066.", "The") and ("In", "1066") are not.
- structure, on a lines.json made in the test: a page with a figure
  between two halves of a paragraph, a caption below it and a word in
  the figure's region gives one paragraph, then the figure block with
  the caption, and one `figure_text` removal; with a hyphen at the line
  before the figure, the word is joined; with the caption beside the
  figure on the same row as a body line, the body line keeps its words.

**Reference pages**, a new excerpt `kadesh_29-38` in
`scripts/fetch_samples.py`, Kadesh's page indices 29 to 38: maps with a
caption below (29, 33), maps set beside the text (36, 38), a caption
inside the map's box and on one row with the text beside it (38), a
caption on the row of a footnote (36), blocks of hieroglyphs (32, 37),
and the other pages text. The implementer checks the expected output by
eye against the page images before it becomes a test, and writes it in
the test:

| page | expected |
|---|---|
| 29 | one figure, its box within 6 pt of the map's frame; caption "MAP 111. The OrootH V«llt-> In tbo Vicimljr of Kadc>.li. 1:500,000 (after Blmekwhorn)" as read; "<•" and "/ifr,yrafex*^Tx" removed as `figure_text`; the paragraph before and after the map one block if the text runs on |
| 33 | one figure, caption "MAP IV. Fint Portions" |
| 36 | the map a figure with caption "MAP V. Second Positions", the footnote's words on its row kept in the footnote; the two lines of hieroglyphs (85 and 82 squares) no figure |
| 37 | the block of hieroglyphs a figure without caption (371 squares) |
| 38 | the map a figure with caption "MAP vi. Third Positions"; "Shabtuna and the position of the Asiatics (No. 7) :" stays in its paragraph |
| 30 to 32, 34, 35 | no figure (32's hieroglyphs make 106 and 78 squares) |

Compared exactly: the figure boxes to 1 pt, the caption's words and
their order, the removed words; by kind, the blocks in order.

**Whole-book tests**, `whole_book`:

- Kadesh: the 17 figures of section 2, on pages 20, 27 (two), 29, 33, 36, 37, 38, 40, 41, 44 (two), 45, 50, 51, 52 and 53, by page and count, the 6 maps with their captions' first two words.
- Haynes and Turney, each skipped when its PDF is absent from
  `samples/`: Haynes has 25 figures, one on each page of section 2,
  each with a caption whose first words are "figure" (any case) and its
  number, 1 to 25, as the OCR read it; Turney has 14 on the pages of
  section 2, 11 with a caption, and no heading on page 174. Only counts, pages and the first
  two words of each caption are asserted, so the test holds no text of
  the books.
- Haskins, Stubbs, Domesday, Mariéjol and Gierke have no figure.

**The fidelity check** (architecture §13) is unchanged: every word of
lines.json is in a block or in a removal, so each `figure_text` word is
recorded, and each caption word is in its figure block.

## 11. Open points

Both are settled; the options are kept for whoever reopens them.

1. **Pictures without a caption, and Kadesh's hieroglyphs.** Settled:
   (a), a picture without a caption is kept, so 11 of Kadesh's blocks
   of hieroglyphs or Arabic become images (orchestrator for the owner,
   18 November 2026). The
   question is whether a smaller picture with no caption next to it is
   kept. Kadesh is where it shows. In the owner's books the pictures
   without a caption, Turney's second cover of page 174, its film still
   of page 167 and its back cover, are of 509 squares or more and are
   kept by each option. With the rule as written, the 11 largest groups of Kadesh's quotations in hieroglyphs
   or Arabic, of 123 to 371 squares, become images in the EPUB, each
   after the paragraph before it, and the smaller ones, single lines
   and short blocks of 43 to 115 squares, do not: they are lost as
   today. The options:
   - (a) as written: a picture of 120 squares or more is a figure with
     or without a caption. The book gains 11 of its quotations as
     pictures and loses the others as today.
   - (b) a figure without a caption label needs 400 squares: no block of
     Kadesh is one (the largest has 371), and every other figure of
     section 2 stays one.
     The EPUB shows no quotation, as today, but none half.
   - (c) every block and line of hieroglyphs: the threshold falls to 43
     squares, and Domesday's stamp, Mariéjol's running head printed as
     a picture and the larger ornaments become figures too.

   Recommendation: (a), because each image kept is text a reader can
   see that the EPUB otherwise loses, and the groups left out are lost
   today too.

2. **The format changes** of section 7. Settled: the four changes are
   accepted, with the explicit field `Figure.kind`, option (a)
   (orchestrator for the owner, 18 November 2026). pages.json gains the in-page
   figures' boxes, `Figure` its kind in words.json and lines.json, and
   blocks.json the removal reason `figure_text`. Other stages and the
   evaluation tool read these files. The options for the kind:
   - (a) the field `Figure.kind`, as written: structure and layout read
     what a figure is.
   - (b) no field: a figure whose box starts at the page's top left
     corner is a plate's, since an in-page figure's box starts inside
     the outer band. It saves two version changes, and ties a meaning
     to a coordinate that the growth into the band (section 3) brings
     within 24 pt of it.

   Recommendation: (a).

## 12. Not in this spec

- Plates and their captions: `docs/specs/plates.md`, structure §18.
- Pictures on pages without a text layer that are not plates: the OCR
  audit (architecture §7b).
- A smaller image for the EPUB: the epub spec.
- Linking "see fig. 2" in the text to its figure: not planned.
- Tables as tables: not planned; a table with a text layer stays text.
