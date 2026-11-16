# Plates: how analyze recognises them and extract cuts their pictures

A plate is a page of a book that is mostly a picture: a map, a drawing,
a photograph, printed on a page of its own. This spec says how analyze
recognises a plate and records the box of its picture, and how extract
cuts that picture into `images/` and reads the plate's text layer, so
that structure can keep the plate's caption as the text of a figure
block and remove the stray words the OCR read in the picture
(`docs/specs/structure.md` §18). The EPUB then shows the picture with
its caption where the plate was printed. Today no stage marks a plate,
so the stray words of the twelve plates of the six sample books run into
the paragraphs around them (Kadesh's page 16, "^U;L", inside the
paragraph of pages 15 to 18).

Dated 16 November 2026. The owner chose this design on 15 November 2026
(architecture §17), out of three: analyze recognising plates from a
small render (this spec); structure alone, from the text layer, which
finds 3 of the 12 plates; and a config key listing the plate pages. It
builds on `docs/architecture.md` and `docs/glossary.md`. analyze and
extract have no spec of their own yet: what they do today is the
walking skeleton's (`docs/specs/walking-skeleton.md` §6), which this
spec changes in the two points below, and which their own specs, with
the OCR audit of architecture §7b, will replace. The numbers come from
the second research of the structure spec (structure §1): on 15
November 2026, galley at commit fb9c8e8 was run on the six whole books,
and a prototype of the rule below on renders of every page, on an Apple
M5 Pro. Page means page index, from 0, in the whole book.

analyze reads the PDF and the config, as now, and the word list of the
book's language (architecture §12), and writes `pages.json`, whose
`PageInfo` gains `picture` (architecture §8, `format_version` 2).
extract reads the PDF, the config and `pages.json`, as now, and writes
`words.json`, whose `PageWords.figures` now holds a plate's figure, and
the plate's image in `images/`.

## 1. The plates of the six books

Plates with a text layer are in two books. The others have none, or
plates without a text layer, which the owner excludes in the config
until analyze has the OCR audit.

| book | page | what it is | its text layer |
|---|---|---|---|
| Kadesh | 16 | a relief, lightly printed | `, ' ..` and `^U;L` (a faint caption) |
| | 19, 24 | maps with the book's running head | "12 THE BATTLE o? KADERH", "JAMES HENRY BREASTED 15"; 24's caption is printed sideways and is not in the layer |
| | 22 | a relief | "PLATE II" |
| | 34, 42, 48, 56, 64 | reliefs and a photograph | "DECENNIAL PUBLICATIONS, V", the series' head, on each; captions on 48, 56 and 64 ("PALIMPSEST WALL SHOWING LATER RELIEFS…") and labels in the picture on 56 ("XXV I XXIV xxm") |
| | 68 | a drawing | "l>i .• I:N\IAL PUBLICATIONS, PLATE VIII", "V", "THE MODERN MODND OF KADESH" |
| | 49, 65 | backs of plates 48 and 64, the picture showing through | `, / .- -`; `a`, `t I` |
| Domesday | 39, 40 | maps, "A LAND OF VILLAGES", "A LAND OF HAMLETS" | 13 and 7 lines of stray words (`^X.^ MoulslVl^rf /\"?`), the caption in two lines, and on 39 the binder's note "[Between pp. 16–17]" |
| Stubbs | 52 to 55 | two maps and their backs | no text layer |
| Kadesh | 17, 23, 35, 43, 57, 69 | plates, backs, and a text page with a figure (69) | no text layer |

Pictures inside text pages (Kadesh's maps on pages 29, 33 and 36, its
lines of hieroglyphs) are not plates and are left out: architecture §8
does not detect figures in text pages yet.

## 2. analyze: recognising a plate

**The rule.** Every page that has a text layer and is not excluded is
rendered at 36 dpi in gray by `pdfium.render`, in the one PDFium thread
(architecture §12); the rest of the work runs in the worker threads,
on the rendered page and the page's words, as pdfplumber reads them.

1. The page is cut into **squares** of 12 by 12 pixels, 24 pt a side,
   from the top left; the squares of the outer ring, which hold the
   scan's edges, are left out, and so is a partial square at the right
   or the foot.
2. A pixel is **ink** when it is darker than the page's median gray by
   more than 25 levels (of 255). A square is **inked** when at least 6%
   of its pixels are ink.
3. A **picture square** is an inked square that no word box touches,
   each box grown by 2 pt on every side.
4. The page is a **plate** when its largest group of picture squares,
   squares that touch side by side (not by a corner) counting as one
   group, has at least 50 squares, and its text layer holds at most 20
   **known words**: words whose key (structure §5) has at least 2
   letters, is made of letters, apostrophes and hyphens, and is in the
   word list, or numbers, digits with brackets or punctuation around
   them ("16", "17]").
5. Its `picture` is the smallest box that holds every picture square of
   the page, in points; its `kind` is `plate` and its `text_source`
   `text_layer`.

A page without a text layer is not tested: with no word boxes, every
line of print would be picture squares. It goes to the OCR audit of
architecture §7b; until analyze has it, it stops the run unless the
config excludes it, as in the walking skeleton.

**Measured.** On the six books' pages with a text layer, the rule finds
all 12 plates of section 1, with groups of 70 to 403 squares and at
most 17 known words (Kadesh 64). It also takes 7 pages that are
pictures but not the book's: Kadesh 0 (the cover), 49 and 65 (backs of
plates), and Mariéjol 1 and 2 (marbled endpapers), 457 and 458 (an
endpaper, the library's card pocket). It takes no text page. The
margins are thin: Mariéjol's page 265, a text page whose OCR failed,
has a group of 107 squares that no word covers and 26 known words,
against the plates' 17 at most; Kadesh's 16, drawn in light gray, has
70 squares against the threshold of 50, and title pages with a
printer's device have 25 or fewer.

| threshold | value | from |
|---|---|---|
| render | 36 dpi, squares of 12 px (24 pt) | guessed: enough to see a picture, cheap to render |
| ink | 25 levels darker than the page's median | measured: at 50, the largest groups of Kadesh 16 and Domesday 39 and 40 fall to 13, 16 and 8 squares, and the three plates are lost |
| inked square | 6% of its pixels | guessed |
| word box grown | 2 pt | guessed |
| largest group | 50 squares | measured: plates 70 to 403, title pages 25 or fewer, Mariéjol 265 107 |
| known words | at most 20 | measured: plates 17 or fewer, Mariéjol 265 26 |

A rule on the text layer alone, a page whose lines mostly fail the
caption test of structure §18, finds Kadesh 16 and Domesday 39 and 40,
misses the other 9 plates of Kadesh, whose lines are heads and
captions, and takes Mariéjol's 16 and 265, pages of garbled text whose
failing lines are words of the book.

The picture's box as written was not measured; the reference pages
check it by eye. On Kadesh 16 the largest group holds 70 of the page's
170 picture squares, so a box of the largest group alone would cut the
lightly printed relief short; the box of every picture square does not.

**Cost.** Rendering every page at 36 dpi took 12.6 s for Domesday's 558
pages on the one PDFium thread, against about 2.5 s for the whole of
`galley2epub layout` on the same book (layout §5). The OCR audit
renders some pages anyway; the two renders are not shared.

## 3. extract: cutting the picture

A `plate` page is read like a `text` page: its words are those of
`page.extract_words()`, and a word inside one of its `exclude_regions`
is a removal, as now. In addition it is rendered at 300 dpi by
`pdfium.render`, the box of its `picture` is cut from the render, its
pixel box rounded outwards, and saved as an 8-bit grayscale PNG,
`images/plate-<page index, 4 digits>.png`, and the page has one
`Figure(box=picture, image="images/plate-0016.png", dpi=300)`. The
walking skeleton's refusal of a `plate` page goes; a page whose
`text_source` is `ocr` is still refused until extract has OCR.

The plate's words keep their place in `words.json`, and layout groups
them as any page's, copying the figure through to `lines.json`;
structure sorts them into the running head, the caption and the stray
words (structure §18).

## 4. The public interface

The pure parts, which tests call on hand-made values:

```python
# galley.analyze

def plate_picture(page: RenderedPage, word_boxes: tuple[Box, ...],
                  known_words: int) -> Box | None: ...
    # The box of the page's picture, in points, when the page is a plate
    # by section 2; None otherwise.

def known_word_count(words: tuple[str, ...], word_list: frozenset[str]) -> int: ...

# galley.extract

def cut_picture(page: RenderedPage, box: Box) -> bytes: ...
    # The PNG of `box`, in points, cut from the page rendered at page.dpi.
```

`run` of each stage is unchanged in what it deletes, checks and writes
(walking-skeleton spec §6), with analyze also taking the word list
(`wordlist.word_list(config.language)`), so `galley2epub` checks for
Tesseract's tools before analyze when the cache lacks the language.

## 5. Cases

- **A plate without a caption** (Kadesh 16): a figure; structure makes
  its two lines `plate_text` and gives a figure block with no text.
- **The back of a plate**, the picture showing through (Kadesh 49, 65),
  a cover, an endpaper or a card pocket: a plate. Its image is cut and
  its legible lines kept as a caption (Mariéjol 458: "DO NOT REMOVE THE
  CARD FROM THIS POCKET"). Such pages belong in the config's
  `exclude_pages`, and the owner adds them.
- **A plate without a text layer** (Stubbs 52 to 55): not tested; the
  owner excludes it, as now, until the OCR audit.
- **A text page whose OCR failed** (Mariéjol 265): 26 known words, not a
  plate.
- **A cover page** in the config's `cover_page` that is also a plate is
  both: `images/cover.png`, rendered whole, and its plate image.

## 6. How it is verified

**Unit tests** on `RenderedPage` values made in the test: a page of
white with a block of black of 10 by 10 squares and no words gives a
box that holds the block; with a word box over most of it, or with 21
known words, `None`; a block of 49 squares, `None`; two blocks of 40
touching only by a corner, `None`; a gray of 20 levels below the
median, `None`. `cut_picture` on a page of 300 dpi gives a PNG of the
box's size in pixels.

**Excerpt tests**, the owner checking each picture by eye before it
becomes a test:

| excerpt | page (excerpt page, book page index) | expected |
|---|---|---|
| `kadesh_8-17` (committed) | 8 (16) | `plate`, its picture holding the relief; every other page `text` (page 9 is excluded) |
| `kadesh_59-68` (new, structure §9) | 5 (64), 9 (68) | `plate`, with their pictures; the other pages `text` but 6 (65) |
| `kadesh_59-68` | 6 (65) | the back of plate 64, `plate` (a known case) |
| `domesday_headings_quotes` (new, structure §9) | 3 (39), 4 (40) | `plate`, the maps as pictures |

A `whole_book` test asserts the pages section 2 measured: the 12 plates
and 7 other pages found in the six books, and no other.

## 7. Not in this spec

- The OCR audit, and what analyze does with a page without a text
  layer: analyze's own spec (architecture §7b).
- Figures inside text pages, and captions beside them: later.
- What structure makes of a plate's words: structure §18.
- How a figure is written in `book.md` and shown in the EPUB: the
  markdown and epub specs.
