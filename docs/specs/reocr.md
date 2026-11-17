# Re-reading small print with Tesseract

galley takes the words of a scanned book from the PDF's **text layer**,
the invisible words an OCR program placed over each page image when the
book was scanned (architecture §1). In small print that layer is often
poor while the scan itself is sharp: in 30 of Gierke's margin notes the
layer has 52 of 139 printed words right and Tesseract, run by galley on
the same notes, 133. This spec says which small print galley reads again
with Tesseract, how it decides, region by region, that Tesseract's
reading is the better one, which stage does it, how the words it
replaces stay accounted for, how it runs, and how it is verified.

Dated 17 November 2026. The owner approved re-reading small print where
the scan is good and the layer poor, and decided that no effort goes to
unreadable scans such as Mariéjol's: the re-reading is not aimed at
them, and where Tesseract reads worse than the layer no word may be
lost. No code of it exists. It builds on `docs/architecture.md` (cited
as "architecture §8"), `docs/glossary.md`, the layout spec
(`docs/specs/layout.md`, "layout §3") and the extract spec
(`docs/specs/extract.md`), whose new reading of the text layer, the
characters in the order the PDF holds them and glued words split at wide
gaps, it assumes. Revised the same day after a review: footnotes are no
longer re-read as part of a whole page, the pages read whole are those
printed wholly in small type (the earlier rule, a share of single
letters, picks no page once the text layer is read in the PDF's order),
no word of a body line is replaced by a note read beside it, and every
number was measured again inside layout's own steps. Revised again the
same day after a second review: the small-print page is found by the
height of its rows, so that every page of an index or of a note set in
small type is read, and a body word is never replaced.

What it decides, in short: the **layout** stage re-reads four kinds of
text, each region on its own, and keeps Tesseract's words for a region
only when they score higher than the layer's by a count of dictionary
words; it records every region it read, with both readings, in
`lines.json`, and layout's fidelity check counts the replaced words.

## 1. Terms

The stages and files this spec talks about (architecture §4 and §8):

- **extract** reads each page's words from the text layer into
  `words.json`. A **word** (`Word` in `src/galley/model.py`) is its
  text, its **box** (`Box`: left, top, right and bottom, in PDF points,
  1/72 inch, from the page's top left) and `ocr_confidence`, Tesseract's
  confidence from 0 to 100, which the text layer's words lack (`None`).
- **layout** groups each page's words into **regions**, the parts of a
  page read one after the other (the body column, a margin, the
  footnotes at the foot), and each region into lines, and writes them
  to `lines.json`. It removes nothing. It runs a **fidelity check**
  before writing (`fidelity.check_stage`): the words of `words.json`
  must be those of `lines.json`, compared as a multiset of strings, so
  that no word is lost or invented without a record.
- **structure** turns the regions and lines into **blocks**, the
  paragraphs, headings, margin notes and index entries of the book, and
  notes, into `blocks.json`.
- `pdfium.render(pdf, page_index, dpi)` is the one way galley renders a
  page into pixels (architecture §12): PDFium, the PDF library, is not
  safe to call from two threads, so every render runs in one thread.
- The **correct stage**, not yet built, will propose fixes to single
  words, using their boxes and confidences (architecture §9).

Those of the domain, besides the glossary's:

- **Margin note**, **outer** and **cut-in** (glossary): an outer margin
  note is printed outside the body column (Gierke, Domesday), a cut-in
  note inside it at its outer side, with the body lines beside it
  shortened (Stubbs). **A side's margin words** are the words layout
  puts outside the body column on that side (layout §3, step 2); **a
  side's cut-in words** those it takes out of the column as cut-in notes
  (step 2b); the **cut-in zone** is the stretch of rows beside a cut-in
  note (step 2b, rule 2).
- **Footnote band**: the small type at the foot of a page, the
  footnotes; layout finds it by the height of its words (layout §3,
  step 4).
- **Re-reading**: rendering a part of a page at 300 dpi and reading it
  with Tesseract, then keeping, for that part, either the layer's words
  or Tesseract's.
- **Region read**: the part of a page that is re-read as one, and on
  which the choice between the two readings is made: one printed outer
  margin note, one crop of cut-in notes, one page's footnote band, or a
  page printed wholly in small type.
- **Page segmentation mode** (psm): Tesseract's setting for what an
  image holds. Mode 3 finds columns and blocks on a whole page; mode 6
  reads the image as one block of lines of the same type.
- **tsv output**: Tesseract's table of what it read, one row per word
  with its box in pixels, its confidence and the numbers of its block,
  paragraph and line.
- **Known word**: a word `wordlist.is_known_word` accepts (architecture
  §12): its key has at least 2 letters and is in the word list of the
  book's language, or it is a number. **Unknown word**: a word that
  holds a letter or a digit and is not known. A word of punctuation only
  is neither.
- **Reading score** of a reading, a sequence of words: its known words
  minus its unknown words, counted after three changes to the words, each
  measured below: quotation marks (‘ ’ “ ” " ') are stripped from both
  ends; "’" inside a word is taken as "'", because the word list writes
  "henry's" and Tesseract writes "Henry’s"; and a word ending in a
  hyphen followed by a word starting with a letter, a word broken at a
  line end ("free-" "holding."), counts once, as known when the two
  joined, or each part, are known, otherwise as the joined word.
- **Small row**: a row of words whose median word height is at most
  0.85 of the book's body word height, layout's own test for the rows
  of a footnote band (layout §3, step 4).
- **Small-print page**: a page with at least 50 words in `words.json`
  on which at least 85 in 100 of the body column's rows of two words or
  more, below the running head, are small rows: a page printed wholly
  in small type, such as an index or a bibliographical note.
- **Token error rate**: the evaluation tool's measure of a text
  against the reference (`docs/specs/evaluation.md` §6): the reference's
  words that galley misses, misreads, splits or glues, plus galley's
  extra words, divided by the reference's words; lower is better.

The books are those of the evaluation set (Haskins, Stubbs, Domesday,
Mariéjol; `docs/specs/evaluation.md` §3), each with its Project Gutenberg
edition as reference, and Kadesh and Gierke, which have none. Page
numbers are page indices of the whole PDF, from 0. Measurements were
taken on 17 November 2026 on a Mac17,9 with 18 cores (6 performance, 12
efficiency), Tesseract 5.5.4 with its `eng` data, pypdfium2 5.15.2,
galley at commit 4542207, 6 worker threads unless said; Gierke's sample
of notes on 16 November 2026 on the same machine.

## 2. What the books show

**Margin notes**, read by eye against the page image: a word is right
when its letters are (case and punctuation ignored); a word broken over
two lines counts once and is right only when both parts are; two words
read as one are both wrong. The layer here is as extract read it before
the extract spec's change.

| book | notes, how chosen | printed words | layer right | Tesseract right |
|---|---|---|---|---|
| Gierke, outer notes | 30, spread over pages 86–185 | 139 | 52 (37%) | 133 (96%) |
| Stubbs, cut-in notes | 46 crops of the cut-in zones of 40 pages spread over the book, the note words wholly inside each crop | 126 | 29 (23%) | 123 (98%) |
| Domesday, outer notes | 25 notes on the 18 pages with notes among 24 pages spread over 22–552 | 113 | 56 (50%) | 102 (90%) |

What the layer does to these notes: it spaces a word out into letters
("M e s s in a ." for "Messina.", Stubbs page 141), glues words
("revoltofthe", page 124), drops lines ("Moral" for "Moral lessons.",
page 22), and garbles ("JK^L" for "March of the barons.", page 178).
Tesseract's errors in the same notes: a misread letter ("tiseal" for
"fiscal", Domesday page 415), two words glued ("towitesand", page 300),
a date read as letters ("LIQI" for "1191", Stubbs page 141), and junk
from a pencil mark, a tick or the edge of a body line beside the note
("~", "Sy AM").

**Stubbs' index** (pages 312–321). With the layer read in the PDF's
order, as the extract spec now reads it, its token error rate at
`blocks.json` falls from 1.543 to 0.129 and the precision and recall of
its entry boundaries are 0.995 and 0.874. Read whole by Tesseract, psm
3, the error rate falls further to 0.096 and the boundaries are 0.984
and 0.955: the recall gains 0.081 (both runs in section 9).

**Footnotes** read better with Tesseract, but their markers, the "1"
or "*" that starts each note, do not. Tesseract reads a marker together
with the next word ("3D.", "1K.") or as a symbol ("®" for "3"), and a
note reference in the text, "Middlesex1", as "Middlesex!": structure
then finds no note to start or to link (section 9 has the runs):

| book | note error rate at blocks, before → after | notes whose reference is right, before → after |
|---|---|---|
| Domesday | 0.090 → 0.083 | 1,279 → 1,204 of 1,729 |
| Haskins | 0.169 → 0.116 | 61 → 55 of 72 |

That is why footnotes are re-read only when the book's config asks
(section 3 and **Open 1**).

**Body text** is not re-read. ocr_lab found the scanner's layer better
than a fresh Tesseract run on 19th-century roman type in all three of
its control books (architecture §7b); a whole page read by Tesseract
also misreads the note references in the body ("Middlesex1" above,
Domesday page 92); and it would cost a full-page Tesseract run per
page, 0.61 to 0.88 s each on Stubbs' index pages, in one thread.

## 3. What is re-read, and the rule that picks it

Four kinds of region are read. For each region read, galley computes the
reading score of the layer's words that the region replaces (section 4
says which) and of Tesseract's words, and **keeps Tesseract's words only
when their score is higher, or equal with more known words** than the
layer's, and they hold at least one word; on a tie with as many known
words or fewer, or lower, the layer's words stay. A tie with more known
words means as many more unknown words: Tesseract read words the layer
lost, some misread. On Haskins' index page 267 the two tie at 250, with
321 known words against 303; the layer, kept before, lost the printed
"10 f.," and "164 ff.;" and read "f." as "/." 18 times, and Tesseract is
right at 36 of the 38 places where the two differ (a by-eye check of 17
November 2026). Measured on the records of whole Stubbs, Domesday,
Haskins and Gierke on 17 November 2026: 423 regions tie; 41 have more
known words in Tesseract's reading, and 34 of them are newly kept (the
others lie over no layer word and fail its rule below): Haskins' page
267, the only small-print page that ties; 5 of Stubbs' cut-in crops;
22 of Domesday's margin notes; 6 of Gierke's. Read by their text, all
but one are the fuller reading ("Precautions taken by Henry I." against
"Precautions taken by"; "Manorial and non- manorial vills." against
"Manorial manorial"); the exception is Gierke's list of page numbers on
page 62, "5 1 56 T" against the layer's "55 56". Keeping the reading
with more words, whatever they are, would take 85 regions, most of
them with junk Tesseract read beside a note. Where the region replaces no word of
the layer, a higher score is not enough: Tesseract's words are kept
only when they hold at least 2 known words (and, as they must score
above the empty layer's 0, more known words than unknown), or when they
hold one known word that is a **sure single word**: it has 4 letters or
more, every word of the reading has a confidence of 80 or more, and no
word of the page's layer may be a reading of the same printed word
(`model.may_read`: under it, or within 16 pt above or below with the
same letters and digits or alike letters, rules (a) to (c) of section
4 taken alone). A reading that holds a word broken at a line end, two
parts scored as one, holds no sure single word ("The pre- cariun.",
Domesday page 325). Junk read over nothing then stays out ("af", Gierke page
120, kept before at a score of 1 against 0: 2 letters, confidence 69),
a note the layer did not read comes in ("Medieval Thought.", Gierke
page 88, 2 known words), and so does a note, or the line of a note, of
one word ("Coronation.", Stubbs page 63, confidence 97; "Henry’s", page
62, 91). The owner asked for the one-word notes on 17 November 2026,
after reading those two on the page images.

The sure single word was measured on the whole of Stubbs, Domesday and
Gierke on 17 November 2026 (galley at 89ed733): 74 regions over no
layer word scored above 0 with one known word. The 34 of Stubbs at
confidence 80 or more are each a printed word of a cut-in note, looked
at on the page images; 8 of them have a layer word of the page that
may read them ("Lewis" beside the body's "Lewis", page 181; "The"
beside the layer's "TheHilde-", page 83), and stay out, since keeping
them could read a word twice; 3 more have fewer than 4 letters ("1165.",
"jou.", "in"). The letters also exclude the numbers of
Gierke's contents lists (pages 63 to 66, "143", confidence 96), which
the layer may have read differently ("14 -3"), its running head's page
numbers ("lix", "ix", 88 and 89), and "on" (Domesday page 427, 95), the
end of "Population" in a table's head. Under 80 lie the pencil marks
and specks ("af" 69, "ww" 57, "NB" 52) and one word not looked at
("Great", Stubbs page 114, 45); the lowest kept is "enemies." (Stubbs
page 95, 81). With these conditions 24 regions are newly kept, 23 of
Stubbs and "Kent." on Domesday page 491; at a threshold of 90 there
would be 22, and at 95, 19, without "Henry’s". The list:
`tmp/slost-threshold.md` of the plan's worktree (not committed).
The choice is made per region, so that a page where Tesseract reads one
note worse keeps the layer for that note and loses no word, and a book
that Tesseract reads worse throughout keeps its layer throughout.

The rule was compared with three others on Stubbs (cut-in notes and
index), before the review, on the layer as read before the extract
change and with Tesseract's words put into `words.json` rather than
inside layout: counting the reference's margin-note words found in
galley's margin notes, each reference note matched to the galley note
sharing most of its words, each galley word used once (a research
script; the evaluation tool scores this from now on, section 10):

| rule | regions where Tesseract's words are kept | margin-note words right, of 1,908 | body error rate at blocks |
|---|---|---|---|
| none (the layer) | 0 | 357 | 0.142 |
| always Tesseract | 417 of 417 | 1,115 | 0.126 |
| Tesseract when it has more known words | 336 of 417 | 1,067 | 0.128 |
| Tesseract when its reading score is higher (chosen) | 351 of 417 | 1,100 | 0.126 |

Counting known words alone rejects regions where the layer spaced a note
into letters ("S Bl t o e i p s h . en of" against "Stephen of Blois.",
page 31, both with 3 known words, since the word list holds "bl" and
"en"); subtracting unknown words takes them. Without taking "’" as "'",
the chosen rule rejected 78 regions instead of 65. Without the quotes
stripped and the broken words joined, it kept the layer where
Tesseract's reading was complete and the layer's not ("‘free-
holding.’", Domesday page 71). Regions where the layer stays although
Tesseract's words hold every word of 2 letters or more of the layer's,
and more besides, remain: 4 of the 98 such regions of Stubbs and 30 of
the 181 of Domesday, in the runs of section 9, most of them because
Tesseract adds a word the word list lacks ("Serf and" against "Serf
and villein.", page 55). A further clause, keeping Tesseract's words
whenever they hold all of the layer's and more, was tried and gave
little: 8 more margin-note words right on Stubbs and 4 more notes found
on Domesday, against the junk it lets in with a complete reading; it is
not part of the rule.

The chosen rule keeps the layer where Tesseract read nothing
("accordance" against nothing, Stubbs page 152), dropped words
("doctrine of Conquest." against "Conquest.", page 248), or read a body
line as junk; and on Gierke's numbered lists of the notes' contents
(pages 61 to 80, "PAGE 192 193 193…" against "16 I 136. F a 138. C") and
its pencil marks.

The four kinds, each with what is cropped and how it is read:

1. **A small-print page** is read whole below its running head: from
   1 pt below the lowest word of the region layout makes of the running
   head (layout §3, step 3) to the page's foot, the page's full width,
   psm 3. The running head and its page number keep the layer's words,
   because the evaluation tool scores them as removals and structure
   finds a running head by its words repeating over pages; Stubbs' guide
   words ("BUR CON"), printed under the running head, are read by
   Tesseract with the rest, and structure still removed the guide
   words of all 10 pages after the re-reading.

   The share of small rows, by page, separates the pages printed wholly
   in small type from the rest with a gap: every page of the indexes of
   Stubbs (312–321, 0.97 to 0.99), Domesday (546–552, 1.00) and Haskins
   (266–273, 0.98 to 1.00), of Haskins' bibliographical notes at the
   ends of its chapters (40, 99, 129, 130, 205, 206, 232, 263, 264, 0.86
   to 1.00), of Mariéjol's bibliography (14–16, 0.93 to 1.00), and
   Domesday's tables 426 and 528 (0.89, 1.00) and Stubbs' publisher's
   list on page 7 (0.87), which is front matter now and not laid out
   as text (analyze, `docs/specs/front-matter.md`); the highest other page is Domesday's 428, a
   table (0.78), then pages of text with long footnotes, Domesday's 290
   (0.77) and Mariéjol's 211 (0.73); Kadesh's highest is 0.57 and
   Gierke's 0.17. The threshold, 0.85, lies in that gap, which is 0.08
   wide. Rows of one word are left out because a page number or a
   catchword is one; the running head is left out because it is set in
   full-size type above an index. Measured on Stubbs, Domesday and
   Haskins as the extract spec reads the layer, on the others as galley
   read it at 4542207, which gives the same word heights. An earlier
   form of this rule, the share of the page's words in layout's
   footnote band, depended on whether layout found a band on the page:
   it took Domesday's index pages 547 and 552 and not 546 or 548 to
   551, and Haskins' 129 and not 130, of the same note.

   Each page is then kept or not by the reading score. Kept: Stubbs'
   10 index pages; Domesday's 528, 547, 548 and 551; Haskins' 99, 129,
   205, 206, 264, 266, 268 and 272. Left as the layer: Stubbs' page 7
   (before it became front matter); Domesday's 426 (Tesseract read its figures as junk), 546, 549, 550
   and 552 (scores within 4 of each other, the layer's index being good
   already); Haskins' other eleven, also within 9. An index is so read
   page by page, some pages from Tesseract and some from the layer;
   each page is the better of the two readings.

2. **Outer margin notes**, on each side of the book that has them: a
   side has them when at least 10% of the book's pages with 50 words or
   more have at least 2 known words among that side's margin words.
   Measured, pages with 2 known margin words, left and right: Gierke 97
   and 88 of 271, Domesday 154 and 165 of 538; Haskins 0 and 0, Stubbs 0
   and 1, Mariéjol 0 and 3, Kadesh 0 and 0. On every page whose body
   column layout places, galley crops that side's **strip**: from 4 pt
   inside the page's edge to 4 pt outside the column's edge, and from 4
   pt above the top of the column's first word to 4 pt below the page's
   lowest word. In the strip it finds the **note bands** by rows of ink,
   as the Gierke measurement did: a pixel is ink below 140 (of 255); a
   pixel row with more than one ink pixel is inked; inked rows separated
   by at most 18 px (4.3 pt) of blank rows are one band; a band less
   than 12 px high, with fewer than 150 ink pixels, or less than 25 px
   wide is a speck or the scan's edge, and dropped; each band is cropped
   to its ink plus 6 px and read with psm 6. Each band is a region read.
   Read as one strip with psm 6 instead, Domesday's notes came out as
   junk ("!@ J , } j" for a whole page side, page 71): the empty strip
   and the clipped ends of body letters confuse Tesseract's line finding.

3. **Cut-in notes**, on each side where the book has a cut-in inset
   (layout §3, "The book's measures"; only Stubbs): each cut-in zone,
   widened by 2.5 body line pitches (the median distance between two
   rows of the body) above and below, and from 3 pt outside the column's
   edge to 3 pt short of the inset (on the left, with the column's edge
   L and the inset I, from L − 3 to L + I − 3 pt), read with psm 6.
   The crop never reaches above the lowest word of the running-head
   region (layout §3, step 3), plus 1 pt: widened by 2.5 pitches, the
   crops of the first notes of a page took the running head's page
   number ("45" read "4)", page 66; "102" read "LOa", page 123).
   Zones whose widened crops overlap are read as one crop. The zone
   alone clips notes, since layout trims it to its shortened rows
   ("Importance" without its second line "of Eng-", page 22). Measured
   before the review, with Tesseract's words always kept and the
   words put into `words.json`: with the zone widened by half a pitch,
   980 of the reference's 1,908 margin-note words were right; by 2.5
   pitches, 1,113; by 4.5, 1,095.

   The widened crop holds pieces of the body lines above and below the
   note, and Tesseract reads them, as words or as junk ("change" read
   "NE", page 49; "pointed" read "ee", page 83; "How long" read "naar
   lawrnme", page 306). So a crop distinguishes the column's words it
   may replace from those it must not: it may replace a word that
   layout left in the column only when the word's vertical middle lies
   within 1 pt of a zone the crop was made from and the word ends at
   least 4 pt short of the inset (on the left, its right side at most
   L + I − 4), the place of a note word; every other word of the column
   in the crop is a **body word**, a word of a full body line or of the
   text beside the note. Then:
   - a line of Tesseract's output (its block, paragraph and line
     numbers) is dropped when one of its words ends within 3 pt of the
     crop's side toward the inset: a body line runs on past it, a note
     line stops 4 pt short of it (layout §3, step 2b);
   - a word of Tesseract's is dropped when its box overlaps the box of
     a body word, whatever it reads: it is a reading of the body line,
     "he was an" before the wide space of a justified line on Stubbs'
     page 57, or junk read off one ("NE");
   - a reading with no word left is never kept, so that a note the
     layer read ("Despensers,", page 306) is not replaced by nothing.

   Of the cut-in words and the column words it may replace, a kept crop
   replaces only those that are the same printed word as one of the
   Tesseract words it keeps (section 4): the note words of a line
   dropped at the inset stay as the layer read them.

   On the whole of Stubbs, with these, the kept crops replaced one word
   that layout had left in the column, "heBarons" on page 226, the OCR's
   reading of the note's "the Barons." that layout's 5 pt guard keeps
   in the body (layout §3, step 2b, rule 3); every other word they
   replaced is a word layout had already taken out as a cut-in word. No
   word of a row outside a cut-in zone, of a running head or of a page
   number was replaced, and 544 of Tesseract's words were dropped as
   overlapping body words. The cost: Tesseract's correct reading of a
   note line whose layer words layout left in the column outside the
   zone is dropped with the rest, and the layer's garbled copy stays in
   the body ("epoch closing with his down- fall.", page 311; "Isabeiia",
   page 307). An earlier form of the second filter dropped a Tesseract
   word only when a body word had the same key, and the region took
   every word inside a kept word's box: on Stubbs it moved 167 words
   out of the column, at least 34 of them body words replaced by
   unrelated text, and dropped note words layout had left in the column
   ("Estimate of", page 50), which a crop may now replace. These counts
   were measured before a kept crop replaced only the layer words under
   its kept Tesseract words (section 4); with that rule it replaces the
   same words or fewer.

   A whole strip down the column's side, with the body lines blanked
   where ink touches the inset, was tried and dropped: it made 2,062
   margin notes of Stubbs' 467, and would replace the layer's body words
   that lie in the strip.

4. **Footnote bands**, only when the book's config has
   `reread_footnotes = true` (**Open 1**): the words of the page's
   footnote band cropped from 3 pt outside the column's left edge to 3
   pt outside its right edge and from 3 pt above the band's highest
   word to 3 pt below its lowest, read with psm 6. One region per page.
   Tesseract's words take the band's place as they are, without layout
   finding the band again from their heights.

Nothing else is re-read: not the body, not a page whose layer spells
its body text out letter by letter, not an index that is not printed wholly in
small type, not Stubbs' chapter summaries. Pages whose `text_source` is
already `ocr` (galley read them with Tesseract because they have no text
layer, such as Kadesh's page 69, architecture §7b) are not re-read.

The config's `ocr` key (architecture §7b) turns it off: with `ocr =
"trust"` layout re-reads nothing, so that a book whose owner trusts its
layer, or a run that must be fast, has no Tesseract in layout. With
`verify`, the default, it re-reads as above; with `redo`, every page is
already Tesseract's, and layout re-reads nothing.

## 4. Which stage, and how words are replaced

**layout does it**, because layout is where the regions are known: the
margins, the cut-in zones, the footnote band. A stage after it would
need these written into `lines.json`, which says nothing of what a
region is (architecture §8); a stage before it would have to find them
again. Doing it in layout also keeps `words.json` the text layer as
read, so that one run of the evaluation tool shows the layer at its
`words` output and the re-reading at `lines`.

layout then reads, besides `pages.json` and `words.json`, the PDF,
through `pdfium.render`, and the config, for `ocr`, `reread_footnotes`
and the language; it runs Tesseract and uses the word list. It writes
`lines.json` as before, with one new field.

The book's measures (layout §3, "The book's measures") are taken from
the layer's words, before anything is re-read, so that they do not
depend on Tesseract. Then, per page, around layout §3's steps:

1. **A small-print page** is decided on the layer's words (steps 1 and
   3 run on them to find the column's rows and the running head), read whole as in
   section 3, and, when Tesseract's words are kept, laid out from them
   by steps 1 to 6. **No other region of a small-print page is read**,
   kept or not: its margins and band are part of the page read.
2. On any other page, the re-reading comes in where each step has found
   its words: after step 2 the outer margin note bands, after step 2b
   the cut-in crops, after step 4 the footnote band. The words kept
   from a region go into the group the replaced words were in (that
   side's margin words, that side's cut-in words, the band), and the
   later steps lay them out as they lay out the layer's.

**The words a region may replace** are:

- for a small-print page, all its words but those of the running-head
  region;
- for a note band, the words of the page whose middle lies within 12 pt
  above or below the band and that reach 2 pt or more into that side's
  margin, past the column's left or right edge (the margin words, and
  the words that cross the edge so far: a body line's last word may end
  1 pt past it, as "of" beside a note on Domesday page 74), or that lie
  under one of its Tesseract words by rule (a) below, as the layer's
  stray letters at the column's edge;
- for a cut-in crop, that side's cut-in words whose vertical middle
  lies within 1 pt of a zone the crop was made from, and the words
  layout left in the column that the crop may replace (section 3, kind
  3); never a body word;
- for a footnote band, the band's words.

**A region replaces, of these, only the words that are the same printed
word as one of its kept Tesseract words** (`model.replaced_layer_words`);
the others stay in the layer. A layer word is that word when

- (a) its middle lies inside the box of one of the Tesseract words
  widened by 2 pt up and down and 1 pt across, and it is of that
  Tesseract word's printed line: the layer words under a Tesseract word
  are taken nearest first, by the distance of their middles from its
  middle up or down, and each is of the line when its box overlaps, up
  and down, the box of every word taken into the line before it. A
  Tesseract word reads one printed line; where the layer's lines lie
  closer than its box widened, a word of the other line under it is
  left to the rules below. A layer word is also matched in (a) when its
  letters and digits, case-folded and not empty, equal those of two or
  three Tesseract words that follow each other in Tesseract's order,
  joined, each with its middle inside the layer word's box widened by
  1 pt: a word the layer glued, "of,96" where Tesseract read "of,"
  "96" (Stubbs' index, page 312; 5 such words on its pages 312 to 321
  stayed beside Tesseract's two, which read them twice); or else
- (b) its letters and digits, case-folded and not empty, equal those of
  one of the Tesseract words whose middle lies within 16 pt above or
  below its own, and that no other layer word has matched.
  A Tesseract word is matched in (a) when a layer word lies under it,
  whatever the texts of the two: it reads that printed word, and (b) and
  (c) pair only the Tesseract words (a) left unmatched. In (b) the pairs
  of a layer word and a Tesseract word of the same text are taken
  nearest first (the distance of their middles across plus up or down),
  each word in one pair at most; or else
- (c) it has 3 letters or more, and its letters, case-folded, are alike
  to those of one of the Tesseract words whose middle lies within 16 pt
  above or below its own and that (a) and (b) left unmatched: difflib's
  `SequenceMatcher` ratio of the two strings of letters is 0.6 or more.
  The pairs are taken nearest first, as in (b), each word in one pair at
  most. A word of fewer than 3 letters, a number among them, needs (a)
  or (b); or else
- (d) it is not a known word as printed (below), and the Tesseract
  words that (a) to (c) left unmatched and whose middles lie inside its
  box, widened by 1 pt across and not at all up and down, are two or
  three that follow each other in Tesseract's order and overlap each
  other up and down, words of one printed line, whatever the texts: a
  word the layer glued and misread, "lo/.," where Tesseract read "10"
  "f.," and "164Jf.;" where it read "164" "ff.;" (Haskins' index page
  267, printed "10 f.," and "164 ff.;"). Without this, keeping
  Tesseract's reading of that page read the two twice. A known word as
  printed is a known word (section 1) that holds nothing but letters,
  digits, apostrophes and hyphens once the marks . , ; : ! ? ( ) and
  quotation marks are stripped from its ends: the layer's misreadings
  are not ("lo/.,", whose key "lo" is in the word list, keeps its "/";
  "164Jf.;", "II.,282", "Godofali"), and a printed word the layer read
  rightly mostly is. The fidelity check, which has no word list, takes
  every layer word as unknown, and so accepts every match layout makes.

  Measured on whole Stubbs, Domesday, Haskins and Gierke on 17 November
  2026. As first written, inside (a) and before (b) and (c), with any
  known layer word and a Tesseract word's middle allowed 1 pt above or
  below the layer word's box, the rule lost printed words: it replaced
  the printed "Devonshire," by Tesseract's junk "a" and "aa"
  (confidences 28 and 27, Domesday page 547); it took for "Unity"
  Tesseract's "Unity" and the "within" of the line below (Gierke page
  103), and for "Definition" the "of the" below (page 181), Tesseract
  words that (b) and (c) would have paired with other layer words. As
  (d) it replaces 5 layer words, each the layer's glued misreading of
  the Tesseract words over it: "lo/.," and "164Jf.;" (Haskins page 267),
  "II.,282" (Stubbs page 320), "Sokeintiie" for "Soke in the" (Domesday
  page 106) and "Godofali" for "God of ail" (Gierke page 224). Without
  the one line, Domesday's "fromdfeam" took Tesseract's "from" "teann-"
  and the "land." of the line below, and the layer's "land." was read
  twice (page 475).

A Tesseract word under which (a) found a layer word of another text
used to stay free for (b) and (c), and then stood for two printed
words: on Domesday page 548 the layer's "dominicum," lay under
Tesseract's "dominieum,", which (c) then paired with the layer's
"Domini" of the line above, where Tesseract had read only "3" for
"Dominium, 224"; "Domini" was lost and "dominieum," read in for both
(review of 17 November 2026). Likewise, without the line of (a), one
Tesseract word took the layer words of two printed lines that both lay
under its widened box: "146" for "14. c" and the "14. c" of the line
below in Gierke's list of page numbers (page 63), "Soca" for "I43" and
"Normans," on Stubbs' index page 318 (the layer's stray "k" under it
overlaps both lines, so a line of the words overlapping the nearest one
alone still took both); the fidelity check (architecture §13) now fails on such
a record.

A printed word that Tesseract did not read, or whose reading a filter
dropped (a cut-in line at the inset, a word over a body word, a word
inside an earlier kept crop), keeps the layer's reading, so no word is
lost. The tolerances were measured on 17 November 2026 on the kept
records of the whole books, pairing each Tesseract word of 3 letters or
more with the nearest layer word of the same text: the layer word's
middle lies within 2 pt of the Tesseract word's box for 95 in 100 of
Domesday's 2,935 pairs and 92 of Gierke's 924 (Stubbs and Haskins: 99
and more); the two middles lie within 8.2 pt of each other, up or down,
for 99 in 100 of Domesday's, and Gierke's layer reads some note lines
up to 15 pt off Tesseract's ("tium" on page 265, "ality." on 248; its
lines of notes lie 1.4 pt lower than Tesseract's at the median). With
16 pt in rule (b), none of Domesday's 421 kept margin-note records and
2 of Gierke's 417 read a word twice by the count below ("reignty" 25 pt
off on page 244, and "147" in a list of page numbers on page 63); with
12 pt, 5 of Gierke's. Rule (a) stays at 2 pt
because a word Tesseract did not read must not fall under its
neighbour: the middle of a Tesseract word lies at least 2.9 pt above the box of the line below for 99 in 100 of
the words of the kept records (Stubbs; 3.4 pt Domesday and Gierke).
Across, the layer places words as Tesseract does, and 2 pt took words
Tesseract did not read into a neighbour's reading ("The" beside the
list number "7" on Gierke page 62; "224" on Domesday page 548), so (a)
widens 1 pt there. Rule (b) takes the layer words that lie further off. Before it, with
rule (a) alone at 1 pt, a printed word was read twice where the layer
placed it off Tesseract's: in 108 of Domesday's 435 kept margin-note
records and 98 of Gierke's 428, counting a record when a layer word that
reaches 2 pt into its margin within 12 pt of the band stays, and its
letters and digits are those of a Tesseract word of the record that no
replaced layer word accounts for (owner, 17 November 2026: a word read
twice is invented text, and not accepted). The rule before that
replaced every word a kept region may replace and lost words: in
hand-made cases of the first code review, a cut-in note's second line
"wcnt nortb", whose Tesseract line was dropped at the inset, and "Sce
Stnbbs" of a footnote band, whose Tesseract words lay inside an earlier
cut-in crop (owner, 17 November 2026).

Rule (c) takes the layer's garbled copies of a word Tesseract read:
the layer reads a note line a few points off the ink and spells it
otherwise ("fllght'" for "flight.", Domesday page 76; "mentofhis" for
"ment of his", Stubbs page 59). Without it, counting a kept margin-note
record when a layer word of 3 letters and digits or more that it left
lies in its band (within 12 pt, and within 2 pt of its crop across) and
has a ratio of 0.6 or more to one of its Tesseract words within 16 pt,
38 of Domesday's 421 kept records and 15 of Gierke's 417 left one (17
November 2026); with it, none of Domesday's and 2 of Gierke's, both
numbers ("131." beside "130.", a list number Tesseract did not read, page
79; "147", page 63). The threshold was set on those 53 words and on the
pairs below it: from 0.5 to 0.6 lie 10 more copies ("sey'" for
"Chertsey.", Domesday page 517; "chy'" for "Monarchy.", Gierke page 115)
but also 4 body words at the column's edge that are no copy ("for"
beside "lord", Domesday page 310; "its" beside "isms.", Gierke page
114; "their" beside "Ethics.", page 270; "has", Domesday page 120);
those 10 copies stay, 7 of Domesday's records and 3 of Gierke's. Of the
58 words (c) replaces on the four books, 10 checked on the page images
(Domesday pages 22, 112, 215, 286, 319, 390, 528, 548; Gierke 183;
Stubbs 59) were each a second reading of a printed word that
Tesseract's reading holds.

**Each word of the layer is replaced by one record at most**: a word
already among the replaced words of a kept region of its page is not
counted again by a later one, and a word of Tesseract's whose middle
lies inside the crop of an earlier kept region on the page is dropped,
and so is one whose letters and digits, case-folded and not empty,
equal those of a Tesseract word of an earlier kept region whose middle
lies within 16 pt above or below its own, when it reads no layer word
the later region may still replace (by the rules above). Two crops
that touch can read the same printed line, whose words' middles lie
outside the earlier crop: in a hand-made case of the review of 17
November 2026, a note band read a line whose middle lay 3 pt below the
band above, which had read and kept it (no such word on whole Stubbs,
Domesday and Gierke). So a printed word is not read in by two regions.
A region not kept drops no word of a later one, whose reading of the same printed
words may then be kept. The regions of a page are taken in the order of
the record below.

**Tesseract's words** become `Word`s with the text of the tsv row,
stripped of spaces; a box in points, the word's pixel box divided by
300/72 and moved by the crop's place on the page; and `ocr_confidence`,
the tsv confidence; in Tesseract's order (block, paragraph, line, word).
The box is the word's own, not its line's: with each word given its tsv
line's top and bottom, as the text layer gives a word the height of its
OCR line, structure took 65 of Haskins' 72 footnotes for body
text after a footnote re-read, because Tesseract's lines of small type
are as tall as the body's words. No word of Tesseract's is dropped for
a low confidence (**Open 2**).

**Tesseract's junk is dropped**: before a region is scored and its
words paired, a Tesseract word with no letter or digit is dropped
unless each of its characters is ordinary punctuation or a sign the
books print: . , ; : ! ? ' " ‘ ’ “ ” ( ) [ ] - – — § & £ $ % * † ‡ ¶ /.
The record counts the words dropped. Tesseract reads a pencil curve or
a stain beside a note as such tokens, and in a kept region they went
into the book: in the kept records of whole Stubbs, Domesday and Gierke
(17 November 2026), 7, 3 and 24 tokens, "|" four times on Gierke page
248, "¥" and "\\" on page 127 (a pencil curve), "©", "@", "~", "_", "¢".
The other tokens with no letter or digit in those records, 100, 20 and
35, are punctuation and stay. A tall "|" also lay over layer words of several lines
(Gierke page 132).

**An underscore at either end of a Tesseract word is junk glued to it**:
"_and" for the printed "and" (Gierke page 88, which the owner read on
the page image on 17 November 2026), "_Ealdor-" (Domesday page 270).
None of the six books prints an underscore: the 170 words of their text
layers that hold one are all garbled ("consists_jn", "A_cccssion",
"_..."), and Tesseract's kept words on whole Stubbs, Domesday and
Gierke held one in those two words only (17 November 2026). So the
underscores at both ends of a Tesseract word are stripped, after the
junk is dropped and before the region is scored and its words paired,
and each word so stripped counts as one junk token in the record's
`dropped_junk_count`. A word of underscores only is junk already.

**The record.** Every region read is a `Reread` in `lines.json`, whether
its words were kept or not (a change to a shared format, **Open 3**):

```python
class RereadKind(StrEnum):
    SMALL_PRINT_PAGE = "small_print_page"  # read whole below its running head
    MARGIN_NOTE = "margin_note"            # one note band of an outer margin
    CUT_IN_NOTE = "cut_in_note"            # one crop of cut-in notes
    FOOTNOTE_BAND = "footnote_band"        # one page's footnote band

@dataclass(frozen=True, slots=True)
class Reread:
    page_index: int
    kind: RereadKind
    box: Box                          # the crop, in points
    layer_words: tuple[Word, ...]     # the words it replaces
    ocr_words: tuple[Word, ...]       # Tesseract's, as above
    layer_score: int
    ocr_score: int
    kept: bool                        # by the rule of section 3
    dropped_junk_count: int = 0       # Tesseract's junk tokens dropped
```

A region where both readings are empty, before Tesseract's junk is
dropped, is not recorded. `LinesFile`
gains `rereads: tuple[Reread, ...]`, in page order and, within a page,
small-print page first, then margin bands top to bottom with the left
side first at the same top, then cut-in crops likewise, then the
footnote band. `lines.json` goes to `format_version` 2.

**The fidelity check** at layout's boundary becomes: the words of
`words.json`, minus the `layer_words` of every kept `Reread`, plus their
`ocr_words`, equal the words of `lines.json` as multisets of strings;
the `layer_words` of each kept `Reread` are words of its page in
`words.json`; no word of the page is among the `layer_words` of two
kept records (compared as page, text and box); and each of a kept
record's `layer_words` is matched to one of its `ocr_words` by rules (a)
to (d) above (`model.replaced_layer_words`, taking no word as known); and, by a test that does not
use that pairing, no Tesseract word of a kept record is the only one of
the record that may read two of its `layer_words` of different printed
lines (architecture §13); so that a record cannot name a word the
layer never had, one another record already replaced, or one that no
word of Tesseract's reads. Every word of the layer is then either in `lines.json` or in
exactly one kept record, with its page and box; a record not kept
changes nothing.

## 5. How Tesseract is called

One module of the package root, `ocr.py`, calls Tesseract, for layout
now and for analyze's audit and extract's OCR pages later (architecture
§7b). It is adapted from ocr_lab's `tesseract_words`
(`lib/common.py`), as the coding skill asks, without its cache:

- `tesseract stdin stdout --psm <n> -l <code> tsv`, the PNG of the crop
  on standard input, with `OMP_THREAD_LIMIT=1` in the environment, so
  that one Tesseract uses one core and the parallelism is galley's;
  `check=True` and a timeout of 120 s (guessed: 100 times the slowest
  whole page measured, 0.88 s, with room for a slow machine).
- Inherited from ocr_lab: a missing language model, or a Tesseract that
  prints plain text, exits with 0; output that does not start with the
  tsv header `level\t` is an `ExternalProgramError` naming the program,
  the language and the start of its error output, never a reading with
  no words.
- Only rows of level 5 (words) with text that is not blank are words.
- The language is `config.tesseract_language(config.language)`.

## 6. The public interface

```python
# galley.ocr

OCR_DPI: Final[int] = 300

def read_image(image: Image.Image, *, origin: tuple[float, float], dpi: int,
               psm: int, language: str) -> tuple[Word, ...]: ...
    # Tesseract's words of `image`, a crop whose top left lies at `origin`
    # on the page, in points, with boxes in points (section 4).

def words_of_tsv(tsv: str, *, origin: tuple[float, float], dpi: int) -> tuple[Word, ...]: ...
    # The pure part of read_image: the words of Tesseract's tsv output.
```

```python
# galley.layout, besides layout §4's functions

def reading_score(words: Iterable[Word], lower_case_words: frozenset[str]) -> int: ...
def is_small_print_page(page: PageWords, measures: BookMeasures) -> bool: ...
def note_bands(strip: Image.Image, *, dpi: int) -> tuple[tuple[int, int, int, int], ...]: ...
    # ValueError when `dpi` is not OCR_DPI: the band's sizes in pixels
    # (section 3, kind 2) were measured at 300 dpi.
    # The note bands of a margin strip, as pixel boxes (section 3, kind 2).
```

`layout_page_with_rereads`, which lays out a page as `layout_page` does
and also gives the records of the regions it read (layout §4), takes
the page's render and Tesseract through the functions it is given, so
that its tests can pass a fixed image and no PDF; `run` gives it a
render by `pdfium.render` at 300 dpi. `run` keeps its signature
(architecture §9). The new config key, in `config.py` and architecture
§6, is `reread_footnotes`, a bool, `false` by default.

## 7. How it runs

layout works page by page in worker threads, as now (layout §5). A
page with a region to read asks the one PDFium thread for a render of
the whole page at 300 dpi, turns it into a Pillow image in the worker,
crops it, and runs Tesseract as a subprocess per region; workers wait on
their subprocesses in parallel. A cropped render would save little:
PDFium took 0.079 s per Domesday page for a 60 pt strip against 0.102 s
for the whole page (40 pages, 100–139). The renders are made one at a
time, so they bound the time. layout with re-reading, on the layer as
the extract spec reads it, 6 workers:

| book | pages | regions read | of them kept | layout in all |
|---|---|---|---|---|
| Stubbs (cut-in notes, small-print pages) | 344 | 365 | 262 | 30.7 s |
| Domesday (outer margins, small-print pages) | 558 | 630 | 443 | 69.9 s |
| Domesday with `reread_footnotes` | 558 | 1,095 | 607 | 77.8 s |
| Gierke (outer margins) | 290 | 762 | 490 | 52.0 s (84.6 s with 1 worker) |
| Haskins (small-print pages) | 280 | 17 | 8 | 3.5 s |
| Haskins with `reread_footnotes` | 280 | 84 | 65 | 11.9 s |

Gierke's run had the rules of this spec but the guard against an empty
reading. layout without re-reading took 2.5 s on Domesday (layout §5).
Mariéjol, without `reread_footnotes`, renders only its three
small-print pages, 14 to 16 (not run through layout). Pages are rendered whole, once each, only when they have a
region; the note bands of a margin are found in the render, so every
page whose column is placed is rendered in a book with outer margin
notes.

The output does not depend on the number of workers: the measures come
from the layer, each page's regions use only its own render and the
book's measures, and Tesseract's output does not depend on what runs
beside it: Stubbs' 417 regions as the first version of this spec read them, before the review, with 1 worker and
with 12 gave byte-identical records, and Gierke's 762 regions read inside layout with 1 worker and with 6 gave byte-identical `lines.json` and records.

## 8. Cases

- **A pencil mark, a tick, a stain in the margin** is a band (7 of 30 of
  Gierke's sample were). Tesseract reads it as short junk ("id i ;"),
  the layer has nothing there, the score is negative, and the layer's
  nothing is kept. Junk of no letter or digit is dropped, beside a real
  note ("~" after "The Hilde-", Stubbs page 83) or alone; junk of
  letters ("id i") is kept with the note when the note wins (**Open
  2**).
- **A note the layer did not read at all** ("Medieval Thought.", Gierke
  page 88; "Fall of Bristol.", Stubbs page 308): the region replaces no
  word, Tesseract's words hold 2 known words or more and more known
  than unknown, or one sure single word ("Coronation.", Stubbs page
  63), and they are kept. Junk read over nothing ("af", Gierke page
  120) has fewer, and is not.
- **A list of numbers in a margin** (Gierke's contents, pages 61–80):
  Tesseract reads the column of page numbers worse, the score keeps the
  layer.
- **A hyphen at a line end** stays a word's last character in both
  readings ("satel-" "lites."), and structure joins it (structure §5);
  the reading score counts the pair once.
- **Two notes in one band**, when less than 4.3 pt apart: one region,
  one choice; layout's own rule then splits them into regions by the
  1.5-pitch gap (layout §3, step 2) as it splits the layer's.
- **A page of text whose footnotes the layer spells out letter by letter** (Domesday 92 and 136,
  Kadesh 61): not a small-print page; its footnote band is re-read only
  with `reread_footnotes`, and its body never.
- **A small-print page that is a table** (Domesday 426): kept as the
  layer by the score.
- **A page with no render to make** (blank, plate, excluded, front
  matter, or read by OCR already): nothing is read.

## 9. How it is verified

**What was measured for this spec.** The runs behind the numbers: galley
at 4542207 ran on Stubbs, Domesday and Haskins through `galley-eval
run`. A research script under `tmp/` (not committed) then rewrote each
book's `words.json` with the extract spec's reading (text flow and the
split of glued words: 104,430 words for Stubbs against the extract
spec's 104,429), and ran `galley2epub layout`, `structure` and
`markdown` and `galley-eval compare`: the **before** column, the layer
as galley will read it, without re-reading. A second script ran
layout's own `run` with its steps patched to re-read as sections 3 and 4
say, then structure, markdown and the comparison: the **after** column.
Scores at `blocks.json`; markdown gives the same.

| score | Stubbs before → after | Domesday before → after |
|---|---|---|
| body token error rate | 0.066 → 0.059 | 0.082 → 0.077 |
| margin notes found as margin notes | 245 → 293 of 467 | 522 → 573 of 593 |
| margin notes missing | 28 → 7 | 41 → 11 |
| margin-note words right (research script, section 3) | 528 → 1,073 of 1,908 | 1,057 → 2,135 of 2,487 |
| index entry boundaries, precision / recall | 0.995 / 0.874 → 0.984 / 0.955 | 0.999 / 0.993 → 0.996 / 0.994 |
| index token error rate | 0.129 → 0.096 | 0.026 → 0.025 |
| notes whose reference is right | – | 1,279 → 1,279 |

Haskins, the same way: index token error rate 0.180 → 0.119, its entry
boundaries 0.997 / 0.988 before and after, body error rate 0.025 →
0.024, notes whose reference is right 61 → 61. No run sets
`reread_footnotes`; the footnote figures of section 2 are from the same
runs with it set. With the earlier filter of cut-in crops (section 3,
kind 3), which replaced body words, Stubbs' margin notes found were 326
and their words right 1,173: the price of replacing no body word is 33
notes and 100 words. On the layer as galley read it at 4542207, before
the extract change, Stubbs' index error rate was 1.543.

**Unit tests**, with literal inputs, no PDF and no Tesseract:

- `words_of_tsv` on a tsv string of two lines of three words, with the
  origin (100, 200) pt and 300 dpi: the boxes in points, the
  confidences, the order; a row of blank text skipped; output without
  the `level` header raises.
- `reading_score`: "Stephen of Blois." scores 3, "S Bl t o e i p s h .
  en of" scores lower (its value written in the test from the word
  list); "Henry’s" counts as known; "‘free-" "holding.’" counts as one
  known word; "." counts as neither.
- `is_small_print_page` on hand-made pages: 50 words in small rows
  is; 49 is not; 17 small rows of 20 (0.85) is, 16 is not; a running
  head of full-size words, and rows of one word, change nothing.
- `note_bands` on a Pillow image drawn in the test: two blocks of ink 30
  px apart give two bands, 15 px apart one; a block 10 px high, and one
  20 px wide, give none.
- A tie: kept when Tesseract's words hold more known words (and as many
  more unknown words) than the layer's; not kept with as many known
  words, or fewer.
- A region over no layer word read as one known word: kept when the
  word has 4 letters and a confidence of 80 ("Coronation."); not kept
  with 3 letters, at a confidence of 79, with a second word under 80,
  or with a layer word of the page that may read it 10 pt below.
- The replacement on a hand-made page: a margin note of three layer
  words replaced by two Tesseract words, a body word beside it kept,
  the layer's single letters inside a Tesseract word's box replaced; in
  a cut-in crop, a Tesseract word over a word of a full body line
  dropped, whatever it reads ("an" over "an", "NE" over "change"), a
  layout's column word in a zone row left of the inset replaced, and
  a reading with no word left not kept; two regions whose
  crops overlap, the second taking no word the first replaced; on a
  small-print page, a margin word read with the page and no margin
  region recorded; a cut-in note line whose Tesseract line is dropped
  at the inset, and a footnote band's words whose Tesseract words lie
  inside an earlier kept cut-in crop, kept as the layer read them. The
  fidelity check passes, and fails when a kept record names a word the
  page does not have, a word another kept record names, or a word that
  none of its Tesseract words lies over or reads. A layer word whose
  line lies 10 pt off Tesseract's, of the same text, is replaced; one
  more than 16 pt off is not; a layer word read twice, once over
  Tesseract's word and once off it, is replaced once. A Tesseract word
  over a layer word of another text pairs with no other layer word
  (Domesday page 548); one over the layer words of two printed lines
  replaces those of the nearer only (Gierke page 63, Stubbs page 318);
  a layer word glued over two or three Tesseract words ("of,96") is
  replaced, over four or with a word outside its box not. A later
  region drops a Tesseract word an earlier kept region read 3 pt below
  its crop, and replaces no word the earlier one replaced. Tesseract's
  "|", "¥" and "\\" are dropped and counted, "—" and "§" kept; "_and"
  is read "and" and counted. The
  fidelity check fails when one Tesseract word is the only reading of
  two layer words of different lines.
  A layer word 6 pt below Tesseract's of alike letters ("fllght'"
  under "flight.") is replaced; one whose ratio is below 0.6 ("for"
  beside "lord") is not; a number of other digits ("131." beside
  "130.") is not; two alike layer words and one Tesseract word: the
  nearer is replaced.
- A config with `reread_footnotes = true`, and one with a string there,
  an error.

**Excerpt tests**, marked `tesseract`, on the committed excerpts. An
excerpt's book measures are taken from its own pages, about ten, so a
page may be a small-print page in the excerpt and not in the book, or
the reverse: Gierke's endnote pages 270 and 271 are small-print pages in
`gierke_86-93_270-271` and not in the whole book, and the index pages
of `stubbs_summaries_index`, six of its ten pages, are not small-print
pages in it, their type being the excerpt's common size (owner, 17
November 2026: accepted as how excerpts work). The tests below are
written against what each excerpt gives. Each
expected reading is a literal of the words galley keeps, written into
the test once the owner has checked it against the page image, as for
every reference page (the coding skill, "Tests"); the literals hold for
Tesseract 5.5.4 with its `eng` data, which the test checks first and
skips, saying so, on another version:

- `gierke_86-93_270-271`, excerpt page 2 (book page 88, the owner's
  page): its four margin notes, the last of which the layer did not
  read ("Medieval Thought.").
- `stubbs_51_56-64`: every cut-in note of the excerpt, as kept; and
  every word of the column that is not a cut-in word of layout, in rows
  outside the zones and right of the inset alike, in the same line as
  in the run without re-reading. "advUers.", the layer's reading of
  the note "advisers." (page 62), ends a body line in both runs, kept in
  the body by layout's 5 pt guard (layout §3, step 2b), and the crop
  that reads the note's "Henry's" there keeps that word alone, a sure
  single word (section 3): Tesseract's "advisers." overlaps the body
  word "advUers." and is dropped with the body's words.
- `stubbs_summaries_index`: no page is a small-print page in the
  excerpt (see above); its index pages are tested on the whole book.
- `domesday_74-83`: the margin notes of two pages, one of which the
  layer garbles.
- `haskins_eval` with `reread_footnotes = true`: a footnote whose marker
  the layer reads "^" is read "1"; and the same excerpt with the default
  reads no footnote band: its one region read is its index page (book
  page 266), a small-print page by section 3.
- Any excerpt with `ocr = "trust"`: `rereads` is empty and `lines.json`
  is what layout gives without re-reading.
- The fidelity check passes on every excerpt, and layout with 1 worker
  and with 6 gives byte-identical `lines.json` on the Stubbs excerpt.

These tests make `uv run pytest` slower: re-reading the Domesday
excerpt's 10 pages costs about 1 s of renders. The excerpt fixture of
`tests/conftest.py` runs the pipeline once per excerpt, so the cost is
paid once.

**Whole-book tests**, marked `whole_book` and `tesseract`: the fidelity
check passes with re-reading on the six books; Stubbs with 1 and 6
workers gives byte-identical `lines.json`; Stubbs' index pages 312 to
321 are small-print pages whose Tesseract reading is kept, their running
heads the layer's, and on page 312 the entry "Acre, siege of, 116; the
English at, 118;" has both ";" (Tesseract's text output of the page has
"116 ;" and "118;").

**The measurement of the plan**, by `galley-eval run` on the four
evaluation books before and after, quoted in its report, with the
margin-note words scored by the tool (section 10). Targets at blocks,
set a little below the after column so that the code's details may move
them: Stubbs' index boundaries at least 0.97 / 0.94; margin notes as
margin notes at least 285 of 467 on Stubbs and 560 of 593 on Domesday;
body error rate at most 0.062 on Stubbs and 0.080 on Domesday;
Domesday's notes whose reference is right at least 1,275; Haskins'
index error rate at most 0.13; Mariéjol unchanged but for its
bibliography, pages 14 to 16; and on Stubbs, no word of the column
that layout did not take as a cut-in word among the `layer_words` of a
kept cut-in record, but "heBarons" (page 226). Gierke has no Gutenberg edition: its margin notes are checked
by eye on the 30 notes of the 16 November measurement, which must stay
at 130 words right of 139 or more.

## 10. Changes to the architecture and other specs

Applied in this branch: `docs/architecture.md` (§1, §4, §6, §7b, §8,
§9, §12, §13, §16, §17), `docs/glossary.md` (known word, note band,
reading score, re-reading, small-print page), `docs/specs/layout.md`
(its opening, §7 and §10) and `docs/specs/evaluation.md` (the part
`margin_notes` of §6 and `ocr_confidence_mean` of §8). Left for the
plan, in the same commits as the code: `src/galley/model.py` (`Reread`,
`RereadKind`, `LinesFile.rereads`, version 2 of `lines.json`), and
layout §3 and §4, which gain the steps and functions of sections 3, 4
and 6 when they are built.

## 11. Open points

1. **Footnote bands: re-read by default or not.** The reader of the
   EPUB sees the difference in the footnotes: with re-reading, more of
   their words are right (Domesday's error rate 0.090 → 0.083, Haskins'
   0.169 → 0.116), and fewer notes open as pop-ups from their reference,
   because Tesseract misreads note markers: Domesday 75 of its 1,279 linked notes lost, Haskins 6 of 61. The options:
   (a) off by default, `reread_footnotes = true` for the books whose
   owner wants it, at no cost to the others; (b) on by default,
   accepting the lost pop-ups; (c) on, but keeping the layer's word at
   the start of each note line where it has a marker's shape, which may
   keep the links and was not measured. Recommended: (a) now, and (c)
   measured in the plan; if (c) keeps the references within 10 of the
   layer's on Domesday, it becomes the default. Meanwhile: (a).
2. **Tesseract's junk in a kept region.** The reader sees a stray mark
   inside a margin note: "The Hilde- ~" for "The Hilde-", "Sy AM The
   Coro- nation," for "The Coronation." A kept region brings with it the
   junk Tesseract read beside the note: on Stubbs' cut-in notes, 74 such
   tokens among 2,213, picked by eye from the list of readings, not
   checked against the images. Dropping kept words under a confidence of
   30 removes 51 of those 74 and 120 of the other 2,139, of which nobody
   has checked how many are real words. Options: keep every word (the
   reader sees the junk; the correct stage can use the confidence); or
   drop words under 30 as removals with a new reason, `ocr_junk`, which
   the owner can review (the reader loses some real words). Recommended:
   keep every word until a sample of the 120 has been read by eye.
   Meanwhile: keep every word. Junk read where the layer has no word
   is a separate case, decided: such a region is kept only with 2 known
   words or more, or one sure single word (section 3).
3. **The new field of `lines.json`, and layout replacing OCR that
   exists** (architecture §7b and §8, applied here): a shared format
   changes, and layout now replaces existing OCR, which §7b had left to
   the owner's choice, though only where Tesseract reads better and with
   every replaced word recorded. The reader of the EPUB sees the margin
   notes and Stubbs' index read by Tesseract. Meanwhile: the plan builds
   against section 4.

## 12. Not in this spec

- **analyze's audit and extract's OCR pages** (architecture §7b): pages
  without a text layer, and the sample that scores the layer against
  Tesseract, are analyze's spec. They use `ocr.py`.
- **Correcting single words** with the vision model, from the
  confidences: the correct stage.
- **Small print in the body column**, Stubbs' chapter summaries and
  quotes, and **body text the layer spells out letter by letter** (Domesday
  481, prose beside a table spelled out letter by letter; Gierke 63 and
  65, contents lists): not re-read. A whole-page re-read would have
  read them better, but also the note references of the page's body.
- **Finding more of Stubbs' cut-in notes**: layout's zones find about
  half (layout §9); the re-reading reads what they find. Of the
  reference's 1,908 margin-note words, 1,073 were right after it.
- **Mariéjol**: no effort aimed at it, by the owner's decision, which
  does not keep the general rules from reaching it. It has no margin
  notes (0 and 3 pages with 2 known margin words) and no footnote is
  re-read by default; its bibliography, pages 14 to 16, after the end
  of its front matter at page 10, is printed in small type (0.93 to
  1.00 of its rows small), so the three pages are small-print pages and
  read whole. Tesseract's reading of page 14 scored 89 against the
  layer's −28 (French word list, psm 3, read by a script outside
  layout), so it would be kept; 15 and 16 were not read. Its highest
  single-letter shares, on which the first version of this spec chose
  whole pages, were 0.189 (page 57) and 0.181 (page 347) as galley read
  the layer at 4542207, and are 0.157 and 0.140 with the extract spec's
  reading, measured by a script that reads the layer as that spec says;
  Stubbs' index pages, 0.24 to 0.63 before, fall below 0.124 with it,
  which is why that rule was dropped.
