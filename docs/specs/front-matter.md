# The front pages: what galley drops before the book's text

A scanned book opens with pages that are not its text: the library's
endpapers and labels, the half-title, the publisher's list of other
books, the title page with its stamps, the copyright line. Their OCR is
often garbage ("•^A V oS -n. ^V/."^-" on Haskins' patterned endpaper,
"lrip>ifl: P. A.. BROCKHAU8" on Domesday's publisher's page), and today
every word of them reaches the EPUB. The owner decided on 17 November
2026 that galley drops the pages before the preface, with a record of
what was dropped. This spec says how analyze finds where the front
matter ends, on books with a preface and on books without one, how the
dropped words are recorded, and what the EPUB shows in their place.

Dated 17 November 2026. It changes analyze and extract, whose rules are
otherwise those of `docs/specs/walking-skeleton.md` §6,
`docs/specs/plates.md` and `docs/specs/extract.md`; it adds a page kind
and a removal reason to the formats of `docs/architecture.md` §8 (cited
as "architecture §8") and a key to the book config (architecture §6),
which the architecture now describes; and it changes how the evaluation
tool scores the dropped pages (`docs/specs/evaluation.md` §5). No code
exists for it. analyze reads the PDF and the book config and writes
`pages.json`; extract reads them and writes `words.json`.

The numbers were measured on 17 November 2026 on the six public-domain
books of `samples/public_domain/`, whole, read as `docs/specs/extract.md`
reads them (Haskins, Stubbs, Domesday, Mariéjol, Gierke and Kadesh, as
that spec names them), with the configs of the `whole_book` tests
(`WHOLE_BOOK_CONFIGS` in `tests/conftest.py`). Page means page index,
from 0, in the whole book.

## 1. Terms

- **Front matter**: the pages of a book before its text, as this spec
  finds them; the preface, when there is one, is text and is kept.
- **Front-matter end**: the index of the first page after the front
  matter. The pages before it are the front matter.
- **Preface page**: a page whose topmost row (the row rule of
  `body_measures.group_rows`, architecture §12) has at most 6 words, one
  of which, reduced to its letters in lower case without accents, is
  "preface", "prefatory", "foreword", "avantpropos", "vorwort",
  "prefazione", "prologo" or "prefacio" (names of a preface in the five
  languages of the config, architecture §6). "PREFACE." on
  Domesday's page 12 is one; "AUTHOR'S PREFACE" would be.
- **The search window**: the first tenth of the book's pages, and at
  least its first 10: 28 pages in Haskins, 34 in Stubbs, 55 in Domesday,
  46 in Mariéjol, 29 in Gierke, 10 in Kadesh. A preface or a table of
  contents printed later than that is not the start of the book's text
  (Mariéjol prints its contents on page 450).

## 2. The rule

analyze finds the front-matter end, after it has classified every page
as walking skeleton §6 and the plates spec say:

1. When the config has `front_matter_end`, it is that.
2. Otherwise it is the first of these two pages in the search window:
   the first preface page; the first page of the config's
   `contents_pages`.
3. When the window holds neither, it is the first page in the window
   whose words number at least half the median number of words of the
   book's text pages: the first page of running text.
4. When the window holds no such page either, it is 0, and nothing is
   dropped.

The pages before the front-matter end that analyze would make `text`
become `front_matter`. The others keep their kind: an excluded page
stays `excluded`, a blank page `blank`, and a plate stays a plate, so
that a map printed as a frontispiece stays in the EPUB as a figure
(Stubbs' "Medieval Europe" on pages 9 and 11, listed as "To face Title"
in its list of maps on page 17).

**Why the preface or the contents, whichever comes first.** A book
prints its preface before or after its contents; either way, everything
before the first of the two is the printer's and the library's (section
4). Gierke has no preface but a translator's introduction (page 12)
after its contents (page 10) and its errata (page 11), which are kept.
Stubbs has neither preface nor introduction: its contents (14 to 16) and
its list of maps (17) come before chapter I (18).

**Why the running text, and why half the median.** Kadesh, an offprint,
has neither a preface nor a table of contents: its text starts on page 8
with 582 words, after a cover, a title page and a copyright page of 6
to 47 words. Half the median is a guess, measured on Kadesh alone: its
49 text pages have a median of 545 words, so the threshold is 272.5, and
every front page has at most 47. The rule is not used when a preface or
contents page is found, because it would stop too early elsewhere:
Stubbs' page 7, the publisher's list of its series, has 299 words, above
half of Stubbs' median of 327.

**When the rule is wrong.** The owner sets `front_matter_end` in the
config: 0 keeps every page, a larger index drops more. analyze logs at
INFO the front-matter end, which of steps 1 to 4 gave it, and the pages
it makes `front_matter`, so that the owner sees what was dropped without
opening `words.json`.

analyze raises `ConfigError` when `front_matter_end` is not below the
page count, as for the other keys of pages (walking skeleton §6,
`check_config_pages`), and when a page of `contents_pages` lies before
it, naming both keys: a contents page that is also dropped is a
contradiction in the config.

## 3. The record

- `PageKind.FRONT_MATTER` (`front_matter`): a page before the
  front-matter end that would otherwise be a text page. Its
  `text_source` is `none`, as an excluded page's is. pages.json goes to
  format version 2.
- `RemovalReason.FRONT_MATTER` (`front_matter`): extract records every
  word of a front-matter page's text layer as a removal with this
  reason, one per word, as it records an excluded page's words with
  `excluded_page` (walking skeleton §6, `page_words`). words.json goes
  to format version 2.
- layout, structure and markdown see a front-matter page as they see an
  excluded page: a page with no words.

A reason of its own, rather than `excluded_page`, because the owner
excludes a page by naming it and galley drops the front matter by a rule
the owner did not check page by page; the record lets the owner, and
the evaluation tool, tell the two apart.

Reading a pages.json or words.json of version 1 is the error of
architecture §8, which names analyze as the stage to run again.

## 4. What is dropped on the six books

| book | front-matter end, and why | pages dropped | words | what they are |
|---|---|---|---|---|
| Haskins | 12, preface | 1, 2, 6, 8, 9, 10 | 108 | patterned endpapers read as garbage (1, 2), half-title (6), title page (8), copyright (9), dedication "TO MY WIFE" (10) |
| Stubbs | 14, contents | 1, 6, 7, 12, 13 | 370 | library label (1), the series' title page (6), the publisher's list of its series (7), title page (12), its back with a library stamp, "'V" (13) |
| Domesday | 12, preface | 4, 8, 9, 10, 11 | 99 | flyleaf with handwriting, "' . L %" (4), half-title (8), publisher's page (9), title page (10), "First Edition 1897. Reprinted 1907." (11) |
| Mariéjol | 10, preface | 6, 7, 8, 9 | 95 | half-title (6), the publisher's list (7), title page (8), rights of translation (9) |
| Gierke | 10, contents | 1, 6, 7, 8, 9 | 100 | binder's label "HANDBOUND AT THE UNIVERSITY OF TORONTO PRESS" (1), half-title (6), publisher's page (7), title page (8), edition (9) |
| Kadesh | 8, first page of running text | 4, 5, 6, 7 | 91 | cover read as garbage (4, 5), title page (6), copyright (7) |

The words are counted after both rules of `docs/specs/extract.md`. The
pages before the end that are not dropped are already excluded by the
config, blank, or plates (Stubbs' 9 and 11). Every dropped page was read
in its text layer; Stubbs' pages 9, 11, 12 and 13 also on the page
image.

## 5. The title in the EPUB

The epub stage does not use the printed title page: Pandoc writes the
EPUB's own title page from the config's `title` and `authors`, which
markdown puts in `book.md`'s metadata header (checked on Haskins' EPUB
of 16 November 2026, Pandoc 3.14: `title_page.xhtml` holds "The Normans
in European History" and "Charles Homer Haskins"). The cover, when the
config has a `cover_page`, is rendered from that page as before, even
when the page is front matter. What the reader no longer sees is what
only the printed front pages hold: a subtitle (Domesday's "Three Essays
in the Early History of England"), the publisher, the date and edition,
and a dedication (Haskins' "TO MY WIFE") (**Open 1**, below).

## 6. How it is verified

- **Unit tests of `front_matter_end`** (section 7) with literal page
  starts: a preface page in the window, a contents page before a
  preface page, a preface past the window (ignored), Kadesh's word
  counts of its 76 pages, as literals (the end is 8), a book with
  neither and no dense page (0), and the config's value winning over
  all.
- **Excerpt tests.** Three new excerpts, cut by
  `scripts/fetch_samples.py`, each with its own config:
  - `haskins_front`: Haskins' pages 1, 2, 8, 9, 10, 12, 13, 14, 16, 17
    and 18 (endpapers, title, copyright, dedication, the two pages of the
    preface, contents, the start of chapter I and two pages with running
    heads), `contents_pages = [7]`. Excerpt pages 0 to 4 are
    `front_matter`, their words the only `front_matter` removals; on
    page 5 (book page 12) layout's first two lines are "PREFACE" and
    "THE eight lectures which are here published".
  - `domesday_front_flow`: Domesday's pages 4, 8, 9, 10, 11, 12, 13, 23,
    24 and 200. Excerpt pages 0 to 4 are `front_matter`.
  - `gierke_front_flow`: Gierke's pages 1, 6, 7, 8, 9, 10, 11, 12, 13
    and 100, `contents_pages = [5]`. Excerpt pages 0 to 4 are
    `front_matter`; 5 (contents) and 6 (errata) are not.
- **The committed excerpts** start inside the book, where the rule could
  take their first pages for front matter (the running-text step on a
  ten-page excerpt that opens with plates). Their configs get
  `front_matter_end = 0`, and their tests are otherwise unchanged by
  this spec.
- **Whole books** (`whole_book` tests): on each of the six books, the
  pages of section 4 and no other are `front_matter`, and the
  `front_matter` removals number as in section 4.
- **The evaluation tool** does not score the reference's words on
  front-matter pages, as it does not score those on excluded pages
  (`docs/specs/evaluation.md` §5, "Pages"): the reference holds
  Mariéjol's and Domesday's title pages, which galley now drops on
  purpose.

## 7. The public interface

analyze gains one pure function, which the unit tests call, and
`classify_page` gains the front-matter end:

```python
# galley.analyze
@dataclass(frozen=True, slots=True, kw_only=True)
class PageStart:
    """What the front-matter rule needs of one page: its index, the kind
    classify_page gives it before the front matter is known, the words
    of its topmost row (empty without words) and its number of words."""
    index: int
    kind: PageKind
    first_row: tuple[str, ...]
    word_count: int

def front_matter_end(starts: tuple[PageStart, ...], config: BookConfig) -> int:
    """The index of the first page after the front matter, by the rule of
    the front-matter spec, section 2: the config's front_matter_end; else
    the first preface page or first contents page in the search window;
    else the first page of running text in it; else 0."""
```

`classify_page(..., front_matter_end: int)` makes `front_matter` a page
before that index that it would otherwise make `text`. extract's
`page_words` gives a `front_matter` page no words and records its layer's
words with `RemovalReason.FRONT_MATTER`. The config key, in
architecture §6:

| key | type, default | meaning |
|---|---|---|
| `front_matter_end` | page index, found by analyze | the first page after the front matter; the text pages before it are dropped with a record. 0 keeps every page |

## 8. Open points

1. **What of the printed front pages the EPUB keeps.** The rule drops
   the dedication with the rest (Haskins' "TO MY WIFE"), and the EPUB's
   title page has the config's title and authors only, without a
   subtitle (Domesday's "Three Essays in the Early History of England").
   The options: (a) keep both out, as decided; nothing to build. (b) A
   config key `subtitle`, written under the title on the EPUB's title
   page (Pandoc's metadata `subtitle`); a line of config and of
   markdown. (c) Keep a dedication page: a dropped page of at most 10
   words that starts with "TO" or "À" becomes a paragraph before the
   preface; a rule to measure, and a dedication is rare in the six
   books (one). The recommendation is (b), and (c) only if the owner
   misses the dedication. **Meanwhile**: (a).

## 9. Not in this spec

- Pages at the end of a book that are not its text (Stubbs'
  advertisements, pages 322 to 328; endpapers and the library's card
  pocket, which the configs exclude): not dropped by this rule.
- How the text-layer words are read: `docs/specs/extract.md`.
- The running head of the preface's second page: structure §3, "The
  head of a short section".
