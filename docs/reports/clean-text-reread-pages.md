# Reference pages changed by task 5.2 (re-reading small print)

17 November 2026. Each reference page whose expected output changed when layout
began to re-read small print with Tesseract (docs/specs/reocr.md, sections 3
and 4), with every region read on it: its kind, the text layer's words it
would replace, Tesseract's words, the two reading scores, and whether
Tesseract's words were kept. Then what changed in the page's expected
layout and blocks. Excerpt page indices are given with the book's page index.
Not yet checked against the page images.

## domesday_74-83_page0 (book page index 74)

- margin_note, kept (3 → 4): `The scale holding.` → `The scale of free- holding.`

Changed: layout, blocks, word changes.

```
-The scale
-holding.
+The scale|of free-|holding.
```

## domesday_74-83_page1 (book page index 75)

- margin_note, not kept (2 → 2): `Free land.` → `Free land.`
- margin_note, kept (-2 → 4): `dOTQ^tht villein.` → `The unfree dom of the villein.`
- margin_note, kept (0 → 3): `Sn°inhbe pursued?` → `Can the villein be pursued ?`

Changed: layout, blocks.

```
-dOTQ^tht|villein.
-Sn°inhbe|pursued?
+The unfree|dom of the|villein.
+Can the|villein be|pursued ?
```

## domesday_74-83_page2 (book page index 76)

- margin_note, kept (0 → 3): `Earity of` → `Rarity of flight.`

Changed: layout, blocks.

```
-Earity of|fllght'
+Rarity of|flight.|fllght'
```

## domesday_74-83_page9 (book page index 83)

- margin_note, kept (1 → 2): `The` → `The Eng- lish for villanus.`

Changed: layout, blocks, word changes.

```
-The Eng-
+The Eng-|lish for Eng-|villanus.
```

## domesday_headings_quotes_page1 (book page index 22)

- margin_note, kept (1 → 5): `Domesday its satei-` → `Domesday Book and its satel- lites.`

Changed: layout, blocks, word changes.

```
-Domesday|its satei-|lltes'
+Domesday|Book and|its satel-|lites.|lltes'
```

## domesday_headings_quotes_page2 (book page index 30)

- margin_note, kept (2 → 5): `Legal ideas` → `Legal ideas of cent. xi.`
- margin_note, kept (0 → 3): `The geo-` → `The geo- graphical basis.`

Changed: layout, blocks, word changes.

```
-Legal ideas
-°
-The geo-
+Legal ideas|of cent. xi.|°
+The geo-|graphical|basis.
```

## domesday_headings_quotes_page5 (book page index 42)

- margin_note, kept (3 → 4): `Size of the` → `Size of the vill.`

Changed: layout, blocks.

```
-Size of the
+Size of the|vill.
```

## gierke_86-93_270-271_page2 (book page index 88)

- margin_note, kept (1 → 2): `Diverse` → `Diverse methods.`
- margin_note, kept (2 → 5): `Unity ment.` → `Unity of the move. ment,`
- margin_note, kept (2 → 4): `Medieval Antique- Thought,` → `Medieval _and Antique- Modern Thought.`
- margin_note, kept (0 → 2): `(none)` → `Medieval Thought.`

Changed: layout, blocks, word changes.

```
-Diverse
-Unity of|ment.
-Medieval|Antique-|Thought,
+Diverse|methods.
+Unity of|the move. of|ment,
+Medieval|_and|Antique-|Modern|Thought.
+Medieval|Thought.
```

## gierke_86-93_270-271_page8 (book page index 270)

- small_print_page, kept (283 → 348): `accept, the distinction between invasions of right (i) legem con- dendo, (2) iudicando, (3) rescribendo, and he is inclined to allow greater force to an act of  …` → `accept, the distinction between invasions of right (1) legem con- dendo, (2) iudicando, (3) rescribendo, and he is inclined to allow greater force to an act of  …`

Changed: layout, notes, word changes.

```
-accept, the distinction between invasions of right (i) legem con-|dendo, (2) iudicando, (3) rescribendo, and he is inclined to allow|greater force to an act of legislation than to acts of other kinds ;|still it is just he who expressly declares that in conflict with Natural|Right, strictly so-calle …
-Tribunals|«£** Pve|Acts of the|jj^J^jjJJ|liberate!?.
-Natural
-the level|£tJJ*
-Coercive
-Force of
+accept, the distinction between invasions of right (1) legem con-|dendo, (2) iudicando, (3) rescribendo, and he is inclined to allow|greater force to an act of legislation than to acts of other kinds ;|still it is just he who expressly declares that in conflict with Natural|Right, strictly so-calle …
+Tribunals|a|Acts of the|a|liberately.
+Natural|= et|the level|—_
+Coercive|SS|Force of|_ of
+et iustitia,’ of which the ‘lex’ is the ‘interpres,’ should govern his|et of which the 'lex' is the should his|will, Then in Aquinas there comes to the front the formula that the|Prince, in so far as the rules of law have no ‘vis coactiva’ against|in so far as the rules of law have no ' vis coactiv …
```

## haskins_eval_page9 (book page index 266)

- small_print_page, kept (182 → 185): `Abacus, 106/. Abruzzi, 196, 204, 222/. Adams, Henry, quoted, 12,22, 188/. Adelaide, countess, 210. Adelard of Bath, 177, 179, 238. Africa, 196/., 222, 232. Aime …` → `Abacus, 106 f. Abruzzi, 196, 204, 222 f. Adams, Henry, quoted, 12, 22, 188 f. Adelaide, countess, 210. Adelard of Bath, 177, 179, 238. Africa, 196 f., 222, 232. …`

Changed: layout, blocks.

```
-Abacus, 106/.|Abruzzi, 196, 204, 222/.|Adams, Henry, quoted, 12,22, 188/.|Adelaide, countess, 210.|Adelard of Bath, 177, 179, 238.|Africa, 196/., 222, 232.|Aime of Monte Cassino, 13, 200/.|Alengon, 63, 178.|Alexander II, Pope,74,79, 165, 175.|Alfred, king, 34.|Alphonso VIII, king, 90.|Amalfi, 197/. …
-Avranchin, 28.|Avre, 7.|Bailli, 103, 145.|Barfleur, 132, 160.|Bari, 189, 197, 202, 232, 241.|Baudri of Bourgueil, 76.|Bayeux, 10, 46, 49, 67, 76, 150 /.,|162,166, 172,187; Black Book, III.|See Odo, Turold, Richard, Philip|d'Harcourt.|Bayeux Tapestry, 76/., 80, 84, 151,|167.|Bayonne, 161.|Bee, 171,  …
+Abacus, 106 f. Avranchin, 28,|Abruzzi, 196, 204, 222 f. Avre, 7.|Adams, Henry, quoted, 12, 22, 188 f.|Adelaide, countess, 210. Bailli, 103, 145.
+Adelard of Bath, 177, 179, 238.|Africa, 196 f., 222, 232.|Aimé of Monte Cassino, 13, 200 f.|Alencon, 63, 178.|Alexander II, Pope, 74, 79, 165, 175.|Alfred, king, 34.|Alphonso VIII, king, go.|Amalfi, 197 f., 204, 213, 232.|Amari, M., 216, 248; quoted, 234.|Anacletus II, Pope, 210.|Andeli, 134.|Anger …
+Barfleur, 132, 160.|Bari, 189, 197, 202, 232, 241.|Baudri of Bourgueil, 76.|Bayeux, 10, 46, 49, 67, 76, 150 f.,|162, 162,166, 166, 172, 187; Black Book, 111.|See Odo, Turold, Richard, Philip|d'Harcourt.|Bayeux Tapestry, 76 f., 80, 84, 151,|167.|Bayonne, 161.|Bec, 171, 185; schools, 175 f.; li-|brar …
```

## stubbs_51_56-64_page9 (book page index 64)

- cut_in_note, not kept (1 → 1): `Banishment` → `Banishment`
- cut_in_note, kept (-2 → 3): `J^tE. Cti°n °£` → `Destruction of castles.`

Changed: layout, blocks.

```
-Cti°n °£|J^tE.
+Destruction of|castles.
```

## stubbs_51_56-64_pages4-5 (book page indices 59 and 60)

Excerpt page 4:
- cut_in_note, kept (-1 → 5): `Silmlnage- children.` → `Henry’s mismanage- ment of his children.`
Excerpt page 5:
- cut_in_note, kept (0 → 3): `reform f` → `Plan of reform.`
- cut_in_note, kept (-1 → 3): `plcificadon.` → `Terms of pacification,`

Changed: word changes only: the hyphen join on excerpt page 4 now joins Tesseract's "mismanage-" to the layer's "mentofhis" (the note's second line, which layout leaves in the column outside the cut-in zone) where it joined the layer's "Silmlnage-".


## Whole-book literals (not reference pages)

- Stubbs, index pages 312 to 321: all ten are small-print pages read
  whole and kept; the guide words of page 312, "BAL BEC", are now found
  (they were a paragraph), the index gives 936 entries for 839, and no
  note is left on the index pages.
- Gierke page 85 (index of authorities): margin_note, kept: `iuris]` →
  `rsi iuris]`. The entry "Tr. U. J. [tractatus universi iuris]" ends at
  "universi", and "rsi iuris]" is a paragraph of its own.

## What to look at on the sheet

- **Words read twice** (reocr spec, section 4, "The price"): a layer word
  that lies under no kept Tesseract word stays beside Tesseract's reading
  of the same printed word. On these pages: "fllght'" beside "flight."
  (Domesday 76), "Eng-" twice (Domesday 83), "lltes'" beside "lites."
  (Domesday 22), "of" twice in "Unity of the move. of ment," (Gierke 88),
  "162, 162,166, 166," (Haskins 266), and on Gierke 270 whole body lines
  ("et iustitia, of which the lex ..." and the layer's "et of which the
  'lex' is the should his"): there 108 of the page's 537 layer words lie
  under no Tesseract word, because the layer's lines on that page sit 4
  to 6 pt below the scan's, more than the 1 pt the rule allows. Also in
  the named test of Haskins 267 (not a reference page file): "Caen, 10
  lo/., f., 71, ...".
- **Gierke 270 and 271 are small-print pages only in the excerpt**: the
  excerpt's book measures come from its 10 pages, two of them these
  endnote pages; in this task's run of layout on the whole book
  no page of Gierke is a small-print page. Tesseract's whole-page reading also
  turns the endnotes' margin notes into "a", "= et", "SS", "—_".
- **Haskins 266, the first four rows of the index read across both
  columns** in layout ("Abacus, 106 f. Avranchin, 28,"): laid out from
  Tesseract's words, the page's first rows are not in the run that step 5
  cuts at the gutter. structure still gives the entries in the order of
  the columns, with the same counts as before (73 entries, 8 of depth 2).

## Changed again by the fix of the words read twice (17 November 2026)

reocr §4 now replaces a layer word (a) under a Tesseract word widened
2 pt up and down and 1 pt across, or (b) of the same letters and digits
as the nearest unmatched Tesseract word within 16 pt up or down. More
layer words are then counted in each region's layer score, so a few
regions are no longer kept.

- domesday_74-83_page9 (book 83): "The Eng- lish for villanus." — the
  layer's second "Eng-" is replaced; the block reads "The English for
  villanus." (was "The English for Engvillanus.").
- gierke_86-93_270-271_page2 (book 88): "Unity of the move. ment," — the
  layer's second "of" is replaced.
- gierke_86-93_270-271_page8 (book 270): small_print_page, now not kept
  (367 → 348): the page is the layer's again, as before task 5.2, and
  its doubled lines are gone.
- haskins_eval_page9 (book 266): "162, 166, 172, 187;" (was "162,
  162,166, 166,"); "Buchanan, James, 17 f." (was "17/. 17 f.").
- Named test of haskins_quotes_index page 9 (book 267): small_print_page,
  now not kept (250 → 250, a tie keeps the layer): "Caen, lo/., 71, ..."
  as before task 5.2.

Still read twice, matched by neither rule (a garbled copy beside
Tesseract's reading): "fllght'" beside "flight." (Domesday 76), "lltes'"
beside "lites." (Domesday 22), and on Gierke 271 the layer's quote marks
"'" "'" and ":" beside Tesseract's "‘in" and "c." (a punctuation mark
has no letters for rule (b)).
- Whole Stubbs: the index gives 935 entries (936 before this fix), page
  312 to 321 still read whole and kept, guide words unchanged.
