# Plates: how analyze recognises them and extract cuts their pictures

A plate is a page of a book that is mostly a picture: a map, a drawing,
a photograph, printed on a page of its own. This spec says how analyze
recognises a plate, and how extract cuts its picture into `images/` and
reads its text layer, so that structure can keep the plate's caption as
the text of a figure block and remove the stray words the OCR read in
the picture (`docs/specs/structure.md` §18). The EPUB then shows the
picture, with its caption, where the plate was printed. Today no stage
marks a plate: the stray words of the plates with a text layer run into
the paragraphs around them (Kadesh's page 16, "^U;L", inside the
paragraph of pages 15 to 18), and the plates without one stop the run
unless the config excludes them.

Dated 16 November 2026. The owner chose this design on 15 November 2026
(architecture §17), out of three: analyze recognising plates from a
small render (this spec); structure alone, from the text layer, which
finds 3 of the 12 plates that have one; and a config key listing the
plate pages. analyze and extract have no spec of their own yet: what
they do today is the walking skeleton's (`docs/specs/walking-skeleton.md`
§6; the walking skeleton is galley's first build, every stage in its
simplest form), which this spec changes in the points below, and which
their own specs, with the OCR audit of architecture §7b, will replace.
It builds on `docs/architecture.md` and `docs/glossary.md`.

The numbers come from renders of every page of the six public-domain
books galley is developed on, made on 15 and 16 November 2026 with
pypdfium2 on an Apple M5 Pro: J. H. Breasted, *The Battle of Kadesh*
(**Kadesh**); O. Gierke, *Political Theories of the Middle Age*
(**Gierke**); C. H. Haskins, *The Normans in European History*
(**Haskins**); W. Stubbs, *The Early Plantagenets* (**Stubbs**); F. W.
Maitland, *Domesday Book and Beyond* (**Domesday**); J.-H. Mariéjol,
*Catherine de Médicis* (**Mariéjol**). Page means page index, from 0, in
the whole book.

analyze reads the PDF, the config and now the word list of the book's
language (architecture §12), and writes `pages.json` in the format of
architecture §8, unchanged. extract reads the PDF, the config and
`pages.json`, and writes `words.json`, whose `PageWords.figures` now
holds a plate's figure, and the plate's image in `images/`.

Revised on 18 November 2026 for the plan stray-text
(`docs/plans/stray-text.md`): analyze also uses the same 36 dpi render
to find an **inkless page**, a page that prints nothing, or only the
next page showing through or a patterned endpaper, while its text layer
holds words the scanner's OCR invented there (section 2b). Such a page
gets the page kind `inkless`, which takes `pages.json` to version 4, and
extract records each of its words as a removal with the reason
`inkless_page` (architecture §8). Without it, those words reach the
EPUB: Haynes' page 9, blank after the contents, gave a paragraph "." and
a heading of five junk words.

## 1. The plates of the six books

| book | page | what it is | its text layer |
|---|---|---|---|
| Kadesh | 19, 24 | maps with the book's running head | "12 THE BATTLE o? KADERH", "JAMES HENRY BREASTED 15"; 24's caption is printed sideways and is not in the layer |
| | 22 | a relief | "PLATE II" |
| | 34, 42, 48, 56, 64 | reliefs and a photograph | "DECENNIAL PUBLICATIONS, V", the series' head, on each; captions on 48, 56 and 64 ("PALIMPSEST WALL SHOWING LATER RELIEFS…") and labels in the picture on 56 ("XXV I XXIV xxm") |
| | 68 | a drawing | "l>i .• I:N\IAL PUBLICATIONS, PLATE VIII", "V", "THE MODERN MODND OF KADESH" |
| | 49, 65 | backs of plates 48 and 64, the picture showing through | `, / .- -`; `a`, `t I` |
| | 17, 23, 35, 43, 57 | reliefs, printed faintly | none |
| | 69 | a photograph with a running head and a few lines of text above it | none |
| Domesday | 39, 40 | maps, "A LAND OF VILLAGES", "A LAND OF HAMLETS" | 13 and 7 lines of stray words (`^X.^ MoulslVl^rf /\"?`), the caption in two lines, and on 39 the binder's note "[Between pp. 16–17]" |
| Stubbs | 9, 11, 52, 54 | maps in colour, two of them folded | none (53 and 55, their backs, are blank) |

Kadesh 16 was in this list, as a relief lightly printed with the stray
words `, ' ..` and `^U;L` in its layer, until the owner looked at it on
16 November 2026: it is not a plate but "the scan of a cover (of the
book or of the plate), no plate and no text". The configs exclude it.
The rule of section 2 still takes it, and the measures of sections 2
and 3 were made with it among the plates, then 22, 12 of them with a
text layer; they are kept as measured. The plates are 21, 11 of them
with a text layer.

Pictures inside text pages (Kadesh's maps on pages 29, 33 and 36, its
lines of hieroglyphs) are not plates and are left out: architecture §8
does not detect figures in text pages yet.

## 2. analyze: recognising a plate

**What is measured.** Every page that is not excluded and is not the
config's `cover_page` is rendered at 36 dpi in gray by `pdfium.render`,
in the one PDFium thread (architecture §12); the rest of the work runs
in the worker threads, on the rendered page and, on a page with a text
layer, the page's words as pdfplumber reads them.

1. The page is cut into **squares** of 12 by 12 pixels, 24 pt a side,
   from the top left. The outer ring of squares, one square wide, is
   left out, because it holds the dark edges of the scan, and so is a
   partial square at the right or the foot.
2. A pixel is **ink** when it is darker than the page's median gray by
   more than a number of levels (of 255): 25 on a page with a text
   layer, 10 on a page without one. A square is **inked** when at least
   6% of its pixels are ink.
3. A **picture square** is an inked square that no word box touches,
   each box grown by 2 pt on every side. On a page without a text layer
   every inked square is one.
4. The **largest group** is the largest set of picture squares that
   touch side by side (not only by a corner).

**A page with a text layer** is a plate when its largest group has at
least 50 squares and its text layer holds at most 20 **known words**,
counting every occurrence. A known word is one for which
`wordlist.is_known_word` is true (architecture §12; structure §18 uses
the same function): its key, the word in lower case with the
characters that are not letters, digits, hyphens or apostrophes
stripped from both ends, has at least 2 letters, is made of letters,
apostrophes and hyphens, and is in the word list, compared in lower
case (242,096 of the 338,080 entries of the English list have a
capital); or it is a number, digits with brackets, hyphens or other
punctuation around them ("16", "17]", "1066-"). Its `kind` is `plate` and its `text_source`
`text_layer`.

**A page without a text layer** is a plate when its largest group holds
at least 0.34 of the page's squares, counted without the outer ring and
without the next column of squares on the left and on the right, where
the shadow of the binding falls (on either side, depending on the
page). Its `kind` is
`plate` and its `text_source` `none`, and it does not stop the run: a
picture without OCR text is still a picture. A page without a text
layer that is not a plate goes to the OCR audit of architecture §7b;
until analyze has it, it stops the run unless the config excludes it,
as in the walking skeleton.

**A page the config names in `plate_pages`** (architecture §6) is a
plate whatever the rule finds, with a text layer or without; a page in
`exclude_pages` is never one. So a plate the rule misses is put in the
book by naming it, and a page it takes wrongly is left out by excluding
it.

analyze logs, at the level WARNING, each page it takes for a plate by
the rule, with its largest group and its known words, so that the owner
sees the covers and endpapers it takes too and can exclude them.

**Measured, pages with a text layer.** The rule finds all 12 plates of
section 1 that have a text layer, with largest groups of 70 to 403
squares and at most 17 known words (Kadesh 64). It also takes 7 pages
that are pictures but not the book's: Kadesh 0 (the cover), 49 and 65
(backs of plates), and Mariéjol 1 and 2 (marbled endpapers), 457 and
458 (an endpaper, the library's card pocket). It takes no text page.
The margins are thin: Mariéjol's page 265, a text page whose OCR failed,
has a group of 107 squares that no word covers and 26 known words,
against the plates' 17 at most; Kadesh's 16, drawn in light gray, has a
group of 70 against the threshold of 50, and title pages with a
printer's device have 25 or fewer.

**Measured, pages without a text layer**, 79 in the six books, on 16
November 2026. The share of the page in the largest group, at an ink
threshold of 10, with the binding columns left out:

| pages | share |
|---|---|
| the plates: Kadesh 17, 35, 43, 57; Stubbs 9, 11, 52, 54 | 0.48 to 0.94 |
| Kadesh 69 (a photograph under text) | 0.36 |
| Kadesh 23 (a faint relief) | 0.26 |
| covers: Mariéjol 0, Stubbs 0 | 0.75 and 0.16 |
| the highest of the others: Kadesh 72 (a blank page, the next page showing through), Domesday 6 (a handwritten note), Domesday 554, Gierke 287 | 0.32, 0.30, 0.29, 0.28 |
| the rest, blank pages among them | 0.26 or less |

With the binding columns counted, as first measured, the shares were
higher, and mostly the binding's shadow: Kadesh 23 was 0.36 and Kadesh
72 0.34. Without them, 0.34 takes 9 of the 10 plates and Mariéjol's
cover, with a margin of 0.02 between Kadesh 69 and Kadesh 72. It misses
Kadesh 23, whose relief is too faint to tell from a page showing
through: the owner names it in `plate_pages`. At the ink threshold of
25 used for pages with a layer, the faint reliefs are hardly ink:
Kadesh 23 has 5 inked squares, as many as a blank page. Kadesh 69 holds a running head
and a few lines of text as well as its photograph; as a plate its
whole page is its picture, so those lines are shown in the image,
though not as text, which needs the OCR audit.

| threshold | value | from |
|---|---|---|
| render | 36 dpi, squares of 12 px (24 pt) | guessed: enough to see a picture, cheap to render |
| ink, page with a layer | 25 levels darker than the page's median | measured: at 50, the largest groups of Kadesh 16 and Domesday 39 and 40 fall to 13, 16 and 8 squares, and the three plates are lost |
| ink, page without a layer | 10 levels | measured, above: at 15, Kadesh 23's group is 0.12 of the page, Domesday 6's 0.27 |
| inked square | 6% of its pixels | guessed |
| word box grown | 2 pt | guessed |
| largest group, page with a layer | 50 squares | measured: plates 70 to 403, title pages 25 or fewer, Mariéjol 265 107 |
| known words | at most 20 | measured: plates 17 or fewer, Mariéjol 265 26 |
| largest group, page without a layer | 0.34 of the page, binding columns left out | measured, above |

A rule on the text layer alone, a page whose lines mostly fail the
caption test of structure §18, finds Kadesh 16 and Domesday 39 and 40,
misses the other 9 plates with a layer, and takes Mariéjol's 16 and
265, pages of garbled text.

**The configs of the sample books.** The 7 pages with a text layer that
are not plates and Mariéjol's cover (page 0, without one) are added to
the `exclude_pages` of the `whole_book` tests' configs
(`WHOLE_BOOK_CONFIGS` in `tests/conftest.py`) and of
`evaluation/books.toml`, or named as the
`cover_page`, and Kadesh 23 to their `plate_pages`, by the plan of this
spec; the `whole_book` test asserts the plates those configs leave,
which are the 21 plates of section 1. The plates without a text layer
are taken out of those `exclude_pages`.

**Cost.** Rendering every page at 36 dpi took 12.6 s for Domesday's 558
pages on the one PDFium thread, against about 2.5 s for the whole of
`galley2epub layout` on the same book (layout §5). The OCR audit
renders some pages anyway; the two renders are not shared.

## 2b. analyze: an inkless page

Some pages of a scan print nothing, yet their text layer holds words:
the OCR read the next page showing through the paper, the pattern of an
endpaper or the speckle of a blank leaf as letters. Haynes' page 9,
blank after the contents, holds 6 such words, among them "SP I fiyj.",
which structure made a heading; Haskins' back endpapers, pages 277 and
278, hold 10 and 24, which became quotes, a footnote and margin notes.
A rule on the words alone cannot tell them from a damaged line of text,
but the render can: under a real word there is ink, under these there
is none. So analyze measures the ink under each word, on the 36 dpi
render it already makes for the plate rule, and nothing more is
rendered.

**What is measured**, on each page the plate rule tests (section 2: not
excluded, not the `cover_page`, not in `plate_pages`) that has a text
layer, for each word of the layer whose middle lies outside the page's
`exclude_regions` (the test extract uses):

1. The word's box, in points, is grown by 3 pt on every side and turned
   into pixels of the render (0.5 pixel per point), its left and top
   sides rounded down and its right and bottom sides rounded up, then
   cut to the page; the same with the box grown by 6 pt. A box that
   lies wholly off the page, as the text layer gives 34 of the 390
   words of Domesday's page 481 ("Cotton" starts at 422 pt on a page
   393 pt wide), has no pixel and counts as a word with no ink.
2. The **local background** is the median gray of the pixels of the box
   grown by 6 pt: the paper around the word, which absorbs a page that
   darkens from one side to the other, as Haynes' page 9 does.
3. The word's **ink** is the larger of two differences, in gray levels
   of 255, over the pixels of the box grown by 3 pt: the local
   background minus the darkest pixel, and the brightest pixel minus
   the local background. The second is for white print on a dark
   ground: Haynes' back cover, page 435, prints its 236 words so, and
   with the first difference alone each would have 0.
4. A word has **no ink** when its ink is below 20 levels.

A page is **inkless** when at least half of those words have no ink. A
page with none of those words is not tested.

**What follows.** A page the test finds inkless gets the kind `inkless`
and the text source `none`, also when the plate rule takes it as a
plate, unless it lies before the front-matter end
(`docs/specs/front-matter.md`): such a page stays `front_matter`, whose
words are removed with a record all the same. Haskins' front endpapers,
pages 1 and 2, are inkless by the test (0.95 and 0.90 of their words
without ink) and stay `front_matter`, as front-matter §6 has them. A page
the config excludes or names in `plate_pages` is not tested and keeps
the kind the config gives it.
It is not `blank`: a blank page is one without a text layer, which
stops the run until the OCR audit exists, while an inkless page has a
layer and its words are kept as a record. extract reads its words as
on any page with a layer and records each as a removal with the reason
`inkless_page`, as it does for an excluded page with `excluded_page`,
but for a word inside one of the page's `exclude_regions`, which keeps
the reason `excluded_region` as on any page;
it has no kept word and no figure, so layout gives it no region and
structure no block. analyze logs each inkless page at WARNING, with its
share of words without ink, so that the owner sees a page taken
wrongly. No config key keeps such a page: the rule takes no page of
print in the eight books (below), and a key is added when a book needs
one.

**Measured** on 18 November 2026 on the eight books named in
`docs/specs/figures.md` (the six public-domain books and the owner's
two), with the words of `words.json` of their runs at main a0a1675,
each word's ink measured as above on a 36 dpi render by pypdfium2.
The front-matter pages were not in this count, their words being
removals in `words.json` (spec review, 18 November 2026: Haskins' pages
1 and 2, above). Of the 1,099,520 words of the pages that are not
inkless, 339 have ink
below 20 levels; of the 43 words of the four inkless pages, 40:

| words | how many | ink below 20 | ink at the 1st percentile | median ink |
|---|---|---|---|---|
| words of 3 characters or more | 827,453 | 73 | 41 | 80 |
| words of 1 or 2 characters | 232,695 | 48 | 38 | 70 |
| punctuation only | 23,634 | 182 | 23 | 57 |
| 1 to 3 digits | 15,738 | 36 | 35 | 68 |
| the words of the four inkless pages | 43 | 40 | | 10 |

The share of a page's words without ink:

| page | share | what it is |
|---|---|---|
| Haynes 9 and 421 | 1.00 | blank pages, another page faintly showing through |
| Haskins 277 | 1.00 | the back endpaper, patterned |
| Haskins 278 | 0.88 | the back endpaper, patterned |
| Domesday 481 | 0.10 | a table whose column heads are printed sideways, each boxed across instead of along its print |
| Turney 176 | 0.07 | a newspaper page reproduced as a figure |
| Gierke 63 and 66 | 0.02 | contents pages whose layer boxes sit 5 to 20 pt off the print |
| every other page | 0.02 or less | |

Haskins 278's share, and the count of its words without ink, are those
analyze gives (21 of its 24 words), measured again on 18 November 2026:
the first measurement, 0.92, came from a render that the investigation's
own script does not reproduce in the project's environment; the other
counts above were not measured again.

So half leaves a margin of 0.38 below the lowest inkless page and 0.40
above the highest page of print. The rule takes Haynes 9 and 421 and
Haskins 277 and 278, and no other page of the eight books that the
configs do not exclude.

| threshold | value | from |
|---|---|---|
| render | 36 dpi, the plate rule's | decided: no second render. At 72 dpi Haskins 278's share falls to 0.58, because the endpaper's pattern is then resolved into ink, and Domesday 481 stays at 0.10 |
| box grown | 3 pt | measured: the layer's boxes sit a few points off the print; of the real words, 2,573 have no ink with the box not grown, 972 grown by 1 pt and 339 by 3 pt, while the four inkless pages keep their shares (Haskins 278 0.88 with each) |
| local background | median of the box grown by 6 pt | guessed, and kept because it absorbs Haynes 9's gradient; the page's median gray, as the plate rule's ink uses, was not tried |
| no ink | below 20 levels | measured, above: 40 of the 43 junk words, 339 of 1.1 million real ones |
| inkless page | at least 0.5 of its words | measured, above |

**A rule per word was measured and dropped.** Removing each word
without ink, wherever it is, would also remove real words. Of 12 words
without ink on pages of print, checked by eye on the page images, 5
were specks of the scan read as letters (Stubbs' "6" on page 33,
Domesday's "e" on page 259) and 7 were real words whose layer box sits
5 to 20 pt off the print (Gierke's "14" on page 63, Domesday's
"Acreage" on 427, Kadesh's "27" on 38), and Domesday's page 481 alone
has 40 real words without ink, its sideways column heads. The page
rule keeps them all.

**Not caught.** Mariéjol's page 459, the back board, is dark and
mottled: its 8 junk words have up to 67 levels of ink, and its share of
words without ink is 0.12, and 0.38 even with a limit of 30 levels. The owner
asked for no effort on Mariéjol's scans, and the page is left as it is.

## 3. extract: cutting the picture

A plate's picture is the **whole page**. Two boxes measured from the
squares were tried on the 12 plates with a text layer, and each was
wrong on some of them: the box of the largest group cuts the lightly
printed relief of Kadesh 16 short (the group holds 70 of the page's 170
picture squares, and its box stops at x = 240 pt of a relief that runs
to about 500); the box of every picture square takes in the next page
showing through (Kadesh 22, where it covers the whole page) and, since
the outer ring is left out, still stops 24 pt short of a picture that
runs to the edge of the scan (Kadesh 16 at x = 432 pt; Kadesh 34;
Domesday 39). The whole page holds every picture of the 22 plates, at
the cost of its margins, the next page showing through where it does,
and the caption, which is then both in the image and in the figure
block's text.

A `plate` page is read as follows:

- with a text layer, its words are those of `page.extract_words()`, and
  a word inside one of its `exclude_regions` is a removal, as on a text
  page; without one, it has no words;
- it is rendered at 300 dpi by `pdfium.render` and saved whole as an
  8-bit grayscale PNG, `images/plate-<page index, 4 digits>.png`, and
  the page has one `Figure(box=Box(0, 0, width_pt, height_pt),
  image="images/plate-0016.png", dpi=300)`. At 300 dpi a page of Kadesh
  is 2118 × 3034 pixels, 2.36 MB as the cover (walking-skeleton spec
  §6), so Kadesh's 15 plates add about 36 MB to the book folder; making
  the EPUB's images smaller is the epub spec's work.

The walking skeleton's refusal of a `plate` page goes; a page whose
`text_source` is `ocr` is still refused until extract has OCR. The
`cover_page` is rendered only as `images/cover.png`, as now, and is
never a figure: analyze does not test it (section 2).

The plate's words keep their place in `words.json`, and layout groups
them as any page's, copying the figure through to `lines.json`;
structure sorts them into the running head, the caption and the stray
words (structure §18).

## 4. The public interface

The pure parts, which tests call on hand-made values:

```python
# galley.analyze

def is_plate(page: RenderedPage, word_boxes: tuple[Box, ...] | None,
             known_words: int) -> bool: ...
    # Whether the page is a plate by section 2; `word_boxes` is None for
    # a page without a text layer, and `known_words` is then ignored.

def is_inkless(page: RenderedPage, word_boxes: tuple[Box, ...]) -> bool: ...
    # Whether the page is inkless by section 2b: at least half of
    # `word_boxes`, the boxes of the page's text-layer words outside its
    # excluded regions, in points, have no ink on `page`, its 36 dpi
    # render. False when `word_boxes` is empty.

# galley.wordlist

def is_known_word(word: str, lower_case_words: frozenset[str]) -> bool: ...
    # `lower_case_words` as `wordlist.lower_case_word_list` gives it.
```

`run` of each stage is unchanged in what it deletes, checks and writes
(walking-skeleton spec §6), with analyze also taking the word list
(`wordlist.lower_case_word_list(config.language)`), so `galley2epub`
checks for
Tesseract's tools before analyze when the cache lacks the language.
analyze's check of the config's page indices (`check_config_pages`)
covers `contents_pages` too.

## 5. Cases

- **A plate without a caption**, whose layer holds only stray words: a
  figure; structure makes its lines `plate_text` and gives a figure
  block with no text. The six books had one, Kadesh 16, until the owner
  found it the scan of a cover (section 1); the unit tests of structure
  §18 keep the case.
- **A plate without a text layer** (Kadesh 17; Stubbs 52): a figure with
  no words, and a figure block with no text.
- **What the rules get wrong, on the six books**: they take as plates 8
  pages with a text layer that are not (Kadesh 0, 16, 49, 65; Mariéjol
  1, 2, 457, 458) and 1 without (Mariéjol 0, a cover), which the configs
  exclude; they miss 1 plate, Kadesh 23, which the config names in
  `plate_pages`. Every page taken by the rule is logged at WARNING.
- **The back of a plate**, the picture showing through (Kadesh 49, 65),
  a cover, an endpaper or a card pocket: a plate, logged. Its image is
  cut and the lines of its layer that pass structure's caption test are
  kept as a caption (Mariéjol 458: "DO NOT REMOVE THE CARD FROM THIS
  POCKET", whose words are known; its stray marks go). Such pages belong
  in the config's `exclude_pages`, and the owner adds them.
- **A text page whose OCR failed** (Mariéjol 265): 26 known words, not a
  plate.
- **The `cover_page`**: never tested, so never a figure. When it is
  excluded too, `images/cover.png` is still made, as now.
- **An inkless page** (section 2b): kind `inkless`, every word a
  removal with the reason `inkless_page`, no figure. A page whose layer
  boxes sit off the print (Gierke 63) or whose words are boxed across a
  sideways print (Domesday 481) has a few words without ink and stays a
  text page with all its words.

## 6. How it is verified

**Unit tests** on `RenderedPage` values made in the test, of 30 by 40
squares: a page of white with a block of black of 10 by 10 squares and
no words is a plate; with a word box over most of it, or with 21 known
words, not; a block of 49 squares, not; two blocks of 40 touching only
by a corner, not; a block of gray 20 levels below the median, not, and
as a page without a text layer covering 0.4 of the squares, a plate,
and covering 0.3, not. `is_known_word`: "Kadesh" with "kadesh" in the
list, "17]", "16" and "1066-" are known, "of" with "of" in the
list is known; "^U;L", "a", "²" and "Fir" with "fir"
absent are not.

**Excerpt tests**, the owner checking each image by eye before it
becomes a test:

| excerpt | page (excerpt page, book page index) | expected |
|---|---|---|
| `kadesh_8-17` (committed) | 8 (16) | excluded in the test's config, the scan of a cover (section 1); every other page `text`, but 9 (17) |
| `kadesh_8-17` | 9 (17) | `plate` without a text layer, no longer excluded in the test's config |
| `kadesh_59-68` (new, structure §9) | 5 (64), 9 (68) | `plate`, with their images; the other pages `text` but 6 (65) |
| `kadesh_59-68` | 6 (65) | the back of plate 64, `plate` and logged (a known case) |
| `domesday_headings_quotes` (new, structure §9) | 3 (39), 4 (40) | `plate`, the maps |

A `whole_book` test asserts, with the configs of section 2, that the
plates of the six books are the 21 of section 1.

**The inkless page** (section 2b). Unit tests of `is_inkless` on
`RenderedPage` values made in the test: a white page with 4 word boxes
over white gives true; with 2 of them each over a black bar 1 pixel
high across the box's middle, true (half); with 3, false; a black page with a white bar, 1 pixel high, under
each of 4 boxes gives false (white print on a dark ground); a page whose gray darkens from 200 on
the left to 120 on the right, with 4 boxes over plain gray, gives true;
no box gives false. A word box 2 pt left of a black bar 1 pixel wide
has ink (the box is grown by 3 pt). Excerpt tests, on pages the
assistant transcribed from their images
(`tests/fixtures/expected/stray_text/`):

| excerpt | page (excerpt page, book page index) | expected |
|---|---|---|
| `haskins_endpapers` (new) | 0 (275) | `text`, the printer's colophon, its words kept |
| `haskins_endpapers` | 1 (276) | `excluded`, as the book's config has it |
| `haskins_endpapers` | 2 (277), 3 (278) | `inkless`, every word a removal with the reason `inkless_page` |
| `domesday_notes` (new) | the excerpt page of 481 | `text`: the sideways table keeps its words |
| `gierke_notes_heads` (new) | the excerpt page of 63 | `text`: the boxes off the print keep their words |

A `whole_book` test asserts that the inkless pages of the eight books,
with the configs of section 2, are exactly Haynes 9 and 421 and Haskins
277 and 278, Haynes' only when its PDF is present.

## 7. Not in this spec

- The OCR audit, and what analyze does with a page without a text layer
  that is not a plate: analyze's own spec (architecture §7b).
- A per-word removal of words without ink, and Mariéjol's page 459:
  section 2b says why not.
- Figures inside text pages, and captions beside them: later.
- What structure makes of a plate's words: structure §18.
- How a figure is written in `book.md` and shown in the EPUB, and a
  smaller image for the EPUB: the markdown and epub specs.
