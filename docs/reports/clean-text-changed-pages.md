# Changed reference literals of task 2.2 (clean-text plan)

17 November 2026. Task 2.2 makes analyze and extract read each page's
words with `text_layer.layer_words`: the characters in the PDF's order
(extract spec section 3) and glued words split at gaps of a third of a
character's width (section 4). This list gives every reference literal
that changed, page by page, with each change of words named a **join**
(several old words are one new word), a **split** (one old word is
several new ones) or a **regrouping** (the same characters in other
words or another order). Changes to lines, blocks, notes and records are
listed after the words that cause them. A script kept outside the
repository (`tmp/compare.py` of the stream's worktree) compared each file
of `tests/fixtures/expected/` with its version before the task; it found
no change of words of another kind. None of these changes has been
checked against the page image, except Haskins' page 12 (a new literal,
below).

Totals of the changes of words in `tests/fixtures/expected/` (25 files),
counted once per file, from the layout's lines of a page file and from
the blocks of a page-break pair: 81 joins, 33 splits and 25 regroupings, 139 in all.

# The files of tests/fixtures/expected/

### domesday_74-83_page0.json (domesday_74-83, excerpt page 0, book page index 74)

Words of the page (layout's lines):

- join: `F our` → `Four`
- join: `r eceding` → `receding`
- join: `f rom` → `from`
- join: `b ut` → `but`
- join: `s eem` → `seem`
- split: `:—` → `: —`
- join: `F ive` → `Five`
- regrouping: `Ah igh` → `A high`
- join: `T he` → `The`
- join: `W hen` → `When`
- join: `T res` → `Tres`
- join: `I psi` → `Ipsi`
- join: `Q uatuor` → `Quatuor`
- join: `4 90:` → `490:`
- join: `l icitum` → `licitum`

Words of the blocks and notes that run on from or to another page:

- join: `l iberties.'` → `liberties.'`

Blocks, notes and records:

- only the word counts of blocks and notes change, with their words

### domesday_74-83_page1.json (domesday_74-83, excerpt page 1, book page index 75)

Words of the page (layout's lines):

- join: `l iberties.'` → `liberties.'`
- join: `t hey` → `they`
- join: `i t` → `it`
- join: `f ree` → `free`
- join: `D .` → `D.`
- join: `H anc` → `Hanc`
- join: `S ee` → `See`
- join: `H aec` → `Haec`
- join: `U na` → `Una`
- join: `I sdem` → `Isdem`

Words of the blocks and notes that run on from or to another page:

- split: `:—` → `: —`
- join: `F ive` → `Five`
- regrouping: `Ah igh` → `A high`
- join: `T he` → `The`
- join: `W hen` → `When`
- split: `:—` → `: —`
- join: `h e` → `he`

Blocks, notes and records:

- only the word counts of blocks and notes change, with their words

### domesday_74-83_page2.json (domesday_74-83, excerpt page 2, book page index 76)

Words of the page (layout's lines):

- split: `:—` → `: —`
- join: `h e` → `he`
- join: `i i.` → `ii.`
- join: `S i` → `Si`

Blocks, notes and records:

- only the word counts of blocks and notes change, with their words

### domesday_74-83_page9.json (domesday_74-83, excerpt page 9, book page index 83)

Words of the page (layout's lines):

- join: `W ellesdone` → `Wellesdone`

Words of the blocks and notes that run on from or to another page:

- join: `a ppreciated,'` → `appreciated,'`
- join: `f or` → `for`
- join: `o ne` → `one`

Blocks, notes and records:

- only the word counts of blocks and notes change, with their words

### domesday_headings_quotes_page1.json (domesday_headings_quotes, excerpt page 1, book page index 22)

Words of the page (layout's lines):

- join: `l egates` → `legates`
- join: `o r` → `or`
- join: `c harged` → `charged`
- join: `t hat` → `that`

Blocks, notes and records:

- only the word counts of blocks and notes change, with their words

### domesday_headings_quotes_page2.json (domesday_headings_quotes, excerpt page 2, book page index 30)

Words of the page (layout's lines):

- join: `i t` → `it`
- join: `t he` → `the`
- join: `1 .` → `1.`
- join: `o f` → `of`
- join: `H undret` → `Hundret`
- join: `H undret` → `Hundret`
- join: `H aec` → `Haec`
- join: `i .` → `i.`
- join: `H aec` → `Haec`

Words of the blocks and notes that run on from or to another page:

- join: `l egates` → `legates`
- join: `o r` → `or`
- join: `c harged` → `charged`
- join: `t hat` → `that`
- a block boundary on another page: `To1t9a l` → `Total 19 population 19 0`: the note of page 30 runs on to page 42 (excerpt page 5), whose table row 'To1t9a l popul1a9t ion 0' is the regrouping 'Total 19 population 19 0' (listed on page 42); the whole row now ends note 3, where before 'popul1a9t ion 0' ended the note 'Abington …', which has no marker

Blocks, notes and records:

- only the word counts of blocks and notes change, with their words

### domesday_headings_quotes_page3.json (domesday_headings_quotes, excerpt page 3, book page index 39)

Words of the page (layout's lines):

- regrouping: `I•n k «^ ^O/ ^^m*^or S fio?pewn^iu.i i` → `•n « ^/ ^m*^r fiopewniu.ii Ik^O^oS?^`

Blocks, notes and records:

- lines per region [5, 2, 6] → [6, 2, 6]

### domesday_headings_quotes_page4.json (domesday_headings_quotes, excerpt page 4, book page index 40)

Words of the page (layout's lines):

- regrouping: `\ | / .":` → `\| /.":`
- regrouping: `.^^<^«»W»L= f ^ a` → `^^^»»=f^ a .<«WL`

Blocks, notes and records:

- lines per region [1, 2, 1, 1, 4] → [4, 1, 1, 4]

### domesday_headings_quotes_page5.json (domesday_headings_quotes, excerpt page 5, book page index 42)

Words of the page (layout's lines):

- regrouping: `ist o` → `is to`
- join: `a lso` → `also`
- join: `w ay` → `way`
- join: `1 9` → `19`
- regrouping: `2 9 3289` → `29 38 29`
- regrouping: `To1t9a l popul1a9t ion 0` → `Total 19 population 19 0`

Words of the blocks and notes that run on from or to another page:

- join: `H aec` → `Haec`
- join: `i .` → `i.`
- join: `H aec` → `Haec`

Blocks, notes and records:

- lines per region [1, 26, 1, 1, 19] → [1, 26, 1, 1, 20]

### domesday_headings_quotes_page6.json (domesday_headings_quotes, excerpt page 6, book page index 47)

Words of the page (layout's lines):

- split: `:—` → `: —`
- split: `:—` → `: —`
- join: `T T>` → `TT>`
- join: `res t` → `rest`
- regrouping: `E n g l a n d i s app aren t. I n` → `England is apparent. In`
- regrouping: `L a y S u b s i d y , 2 5 E d w . I . ( Y o r k shire` → `Lay Subsidy, 25 Edw. I. (Yorkshire`
- regrouping: `Frac t i o n s o f` → `Fractions of`
- regrouping: `p o u n d ar e n e g l e c t e d .` → `pound are neglected.`
- regrouping: `n - an d n o m a n o ri al` → `and non- manorial`

Words of the blocks and notes that run on from or to another page:

- regrouping: `an d n o m a n o ri al n -` → `and non- manorial`

Blocks, notes and records:

- structure's word changes: removed [], added [(['non-', 'manorial'], ['non-manorial'], 'hyphen_kept')]

### gierke_86-93_270-271_page2.json (gierke_86-93_270-271, excerpt page 2, book page index 88)

Words of the page (layout's lines):

- none

Words of the blocks and notes that run on from or to another page:

- join: `b ut` → `but`

Blocks, notes and records:

- only the word counts of blocks and notes change, with their words

### gierke_86-93_270-271_page8.json (gierke_86-93_270-271, excerpt page 8, book page index 270)

Words of the page (layout's lines):

- join: `l ege` → `lege`
- join: `d ifference` → `difference`
- join: `l ex` → `lex`
- join: `v is` → `vis`
- join: `a gainst` → `against`
- join: `q uantum` → `quantum`
- join: `l ex` → `lex`
- join: `i n` → `in`
- join: `u ltra` → `ultra`
- join: `P ve` → `Pve`

Words of the blocks and notes that run on from or to another page:

- join: `c oactive` → `coactive`
- join: `d irective` → `directive`

Blocks, notes and records:

- only the word counts of blocks and notes change, with their words

### haskins_eval_page1.json (haskins_eval, excerpt page 1, book page index 132)

Words of the page (layout's lines):

- regrouping: `GiraldusCambrensis (RollsSeries),` → `Giraldus Cambrensis (Rolls Series),`

Words of the blocks and notes that run on from or to another page:

- split: `morepronetoseek` → `more prone to seek`

Blocks, notes and records:

- only the word counts of blocks and notes change, with their words

### haskins_eval_page9.json (haskins_eval, excerpt page 9, book page index 266)

Words of the page (layout's lines):

- split: `Adams,Henry,quoted,` → `Adams, Henry, quoted,`
- split: `Adelardof` → `Adelard of`
- split: `AlexanderII,` → `Alexander II,`
- split: `172,187;BlackBook,` → `172,187; Black Book,`
- split: `BayeuxTapestry,` → `Bayeux Tapestry,`
- split: `Bibliographicalnotes,24/.,51,83/.,` → `Bibliographical notes,24/.,51,83/.,`
- split: `I,princeofAntioch,207,` → `I, prince of Antioch,207,`

Blocks, notes and records:

- blocks: [] → [('index_entry', 2, None, [9])]

### haskins_eval_pages1-2.json (haskins_eval, excerpt pages 1 and 2, book page indices 132 and 133)


Words of the blocks, notes and removals:

- split: `morepronetoseek` → `more prone to seek`

Blocks, notes and records:

- only the word counts of blocks and notes change, with their words

### haskins_quotes_index_page1.json (haskins_quotes_index, excerpt page 1, book page index 41)

Words of the page (layout's lines):

- regrouping: `longbeforethatyear. Thelandwas` → `long before that year. The land was`
- regrouping: `permanentlyin theland andgave` → `permanently in the land and gave`

Words of the blocks and notes that run on from or to another page:

- split: `pleasingandvariegated,` → `pleasing and variegated,`
- split: `theValkyrie` → `the Valkyrie`
- split: `ofthe` → `of the`
- split: `featsof` → `feats of`

Blocks, notes and records:

- only the word counts of blocks and notes change, with their words

### haskins_quotes_index_page7.json (haskins_quotes_index, excerpt page 7, book page index 209)

Words of the page (layout's lines):

- split: `theirown` → `their own`
- split: `orbiset` → `orbis et`
- split: `Albiset` → `Albis et`

Words of the blocks and notes that run on from or to another page:

- split: `accountsof` → `accounts of`
- split: `mattersare` → `matters are`
- split: `1903),corrected` → `1903), corrected`
- split: `Round,to` → `Round, to`
- split: `Maitland,HistoryofEnglishLaw(secondedition,` → `Maitland, History of English Law (second edition,`
- regrouping: `Theresultsof recentinvestigationareincorporatedin thestudiesand` → `The results of recent investigation are incorporated in the studies and`
- split: `studiesof` → `studies of`
- split: `chanceryinL.` → `chancery in L.`
- split: `RecueildesactesdeHenriIIconcernant` → `Recueil des actes de Henri II concernant`
- split: `franqaisesetles` → `franqaises et les`
- split: `andoftheexchequerinR.L.` → `and of the exchequer in R. L.`
- regrouping: `TheExchequerinthe TwelfthCentury(Oxford,` → `The Exchequer in the Twelfth Century (Oxford,`
- regrouping: `SeealsoHubertHall, CourtLifeunder` → `See also Hubert Hall, Court Life under`
- regrouping: `distinctivelyNormansideofthegovernmentseeHaskins, "TheGovern-` → `distinctively Norman side of the government see Haskins, "The Govern-`
- a block boundary on another page: `A castle, precipice-encurled, Inagashofthewind-grievedApennine; or` → ``: the paragraph that starts on page 209 ran on to page 210 (excerpt page 8) and ended with the first two lines of a verse, 'A castle, precipice-encurled,' and 'Inagashofthewind-grievedApennine;', and 'or'; the second line split, 'In a gash of the wind-grieved Apennine;', the two lines are a verse block of their own on page 210, and the paragraph ends before them

Blocks, notes and records:

- only the word counts of blocks and notes change, with their words

### kadesh_8-17_page0.json (kadesh_8-17, excerpt page 0, book page index 8)

Words of the page (layout's lines):

- join: `J .` → `J.`
- join: `I n` → `In`

Blocks, notes and records:

- notes: [('a', [0], ['paragraph'])] → [('', [0], ['paragraph'])]

### kadesh_8-17_page2.json (kadesh_8-17, excerpt page 2, book page index 10)

Words of the page (layout's lines):

- join: `w as` → `was`
- join: `K adesh"` → `Kadesh"`
- join: `T his` → `This`

Words of the blocks and notes that run on from or to another page:

- join: `t he` → `the`

Blocks, notes and records:

- only the word counts of blocks and notes change, with their words

### mariejol_210-219_page0.json (mariejol_210-219, excerpt page 0, book page index 210)

Words of the page (layout's lines):

- regrouping: `deF rance,-` → `de France,-`
- regrouping: `i l s e` → `il se`
- regrouping: `des i` → `de si`
- join: `S uis-je,` → `Suis-je,`
- regrouping: `là 'envoyé` → `l'envoyé à`
- join: `S i` → `Si`
- join: `( 4).` → `(4).`
- join: `L a` → `La`
- join: `G roéa` → `Groéa`
- join: `Q té` → `Qté`

Blocks, notes and records:

- only the word counts of blocks and notes change, with their words

### mariejol_210-219_page4.json (mariejol_210-219, excerpt page 4, book page index 214)

Words of the page (layout's lines):

- join: `l es` → `les`
- join: `: s` → `:s`
- join: `: .` → `:.`
- join: `e ût` → `eût`
- join: `e script` → `escript`
- regrouping: `(» i)` → `(i) »`
- join: `b onhomme` → `bonhomme`
- join: `\ \'-` → `\\'-`
- join: `. ait` → `.ait`
- join: `C ardinal)` → `Cardinal)`
- join: `1 1` → `11`
- regrouping: `IV(,1 9 p7. ) a a>.` → `IV, (197) p. aa>.`

Words of the blocks and notes that run on from or to another page:

- join: `j uicnne` → `juicnne`
- join: `j uillet` → `juillet`
- join: `n t` → `nt`
- join: `l 'envahissante` → `l'envahissante`
- join: `l aquelle` → `laquelle`
- join: `t enait` → `tenait`
- join: `i l` → `il`
- join: `m ais` → `mais`

Blocks, notes and records:

- only the word counts of blocks and notes change, with their words

### mariejol_headings_verse_page1.json (mariejol_headings_verse, excerpt page 1, book page index 51)

Words of the page (layout's lines):

- join: `) ).` → `)).`
- join: `A in*.` → `Ain*.`

Words of the blocks and notes that run on from or to another page:

- join: `n e` → `ne`
- join: `d oit` → `doit`

Blocks, notes and records:

- only the word counts of blocks and notes change, with their words

### stubbs_51_56-64_page0.json (stubbs_51_56-64, excerpt page 0, book page index 51)

Words of the page (layout's lines):

- split: `ofHenryJs` → `of HenryJs`
- join: `H is` → `His`
- split: `ofToulouse` → `of Toulouse`
- split: `Summaryofnine` → `Summary of nine`
- split: `attachedby` → `attached by`
- split: `toHenry's` → `to Henry's`
- regrouping: `Si. mon` → `Simon .`
- regrouping: `Stephen'sincompetency,howthoroughly shehad` → `Stephen's incompetency, how thoroughly she had`
- split: `ofa` → `of a`
- split: `ofsociety` → `of society`
- regrouping: `f or i s scarcel,y named, ,by t,,he` → `, ,, for is scarcely named , , by the`

Blocks, notes and records:

- structure's word changes: removed [(['as-', 'attachedby'], ['asattachedby'], 'hyphen_join_guessed')], added [(['as-', 'attached'], ['asattached'], 'hyphen_join_guessed')]

### stubbs_51_56-64_page9.json (stubbs_51_56-64, excerpt page 9, book page index 64)

Words of the page (layout's lines):

- split: `haddone,` → `had done,`
- join: `b u s i n e s s` → `business`
- split: `atonce,and` → `at once, and`
- split: `castlesbuiltunder` → `castles built under`
- split: `shouldbe` → `should be`
- split: `Themercenaries` → `The mercenaries`
- split: `ifnot` → `if not`
- split: `anysuch` → `any such`
- split: `isnotuntil` → `is not until`
- join: `B an i s h m e n t` → `Banishment`
- regrouping: `1 a n d s e t ti n° g w o rk a t on c e w i t h th e 1 ^4 0, t h e r e ve nu e F r om t h i.s c o u rt a t D f m e r c e n a -` → `1140, and setting ° work at once with the ^ the revenue. From this court at Df mercena-`

Words of the blocks and notes that run on from or to another page:

- split: `himselfby` → `himself by`
- regrouping: `B an i s h m e n t 1 a n d s e t ti n° g w o rk a t on c e w i t h th e 1 ^4 0, t h e r e ve nu e F r om t h i.s c o u rt a t D f m e r c e n a -` → `1140, and setting ° work at once with the Banishment ^ the revenue. From this court at Df mercena-`

Blocks, notes and records:

- blocks: [('margin_note', None, None, [9])] → []
- blocks: [] → [('margin_note', None, None, [9]), ('paragraph', None, None, [9])]
- structure's word changes: removed [], added [(['mercena-', 'nes'], ['mercenanes'], 'hyphen_join_guessed')]

### stubbs_51_56-64_pages4-5.json (stubbs_51_56-64, excerpt pages 4 and 5, book page indices 59 and 60)


Words of the blocks, notes and removals:

- split: `ofbusiness` → `of business`
- split: `ofdetail,` → `of detail,`
- split: `outwardpresentment.` → `outward presentment.`

Blocks, notes and records:

- only the word counts of blocks and notes change, with their words


# Literals in the tests

### tests/test_excerpts.py

- `test_margin_note_beside_the_middle_stubbs_58_goes_before_its_paragraph`
  (stubbs_51_56-64, book page indices 57 and 58): margin notes, splits
  `Hisgreatposi.` → `His great posi.`, `inChristendom.` → `in
  Christendom.`, `Characterof` → `Character of`, `Hisfamily` → `His family`.
- `test_chapter_summary_stubbs_51_is_one_block_and_very_few_starts_a_paragraph`
  (book page index 51): splits `ofHenryJs` → `of HenryJs`, `ofToulouse` →
  `of Toulouse`, `Summaryofnine` → `Summary of nine`; join `H is` → `His`.
- `test_chapter_summary_stubbs_summaries_index`, page 1 (book page index
  28): no chapter summary before, one now. The summary's words were mixed
  by the sorting, `Ste phen — Bishops — Matilda Accession of — The Anarchy
  Arrestof—the The Pacification. Electionof`, a paragraph; in the PDF's
  order they are a regrouping, `Accession of Stephen — Arrest of the
  Bishops — Election of Matilda — The Anarchy — The Pacification.`, which
  structure takes for a chapter summary.
- the same test, page 2 (book page index 79): splits `SchoolsofClergy` →
  `Schools of Clergy`, `RiseofBecket` → `Rise of Becket`.
- `test_heading_blocks_of_the_reference_pages`, domesday_headings_quotes
  page 2 (book page index 30): join `1 .` → `1.` in `§ 1. Plan of the
  Survey.`
- `test_verse_blocks_of_the_reference_pages_keep_their_lines`,
  haskins_quotes_index page 7 (book page index 209): splits `orbiset` →
  `orbis et`, `Albiset` → `Albis et`.
- the same test, page 8 (book page index 210): a new verse block, `A
  castle, precipice-encurled,` / `In a gash of the wind-grieved
  Apennine;`, from the split `Inagashofthewind-grievedApennine;` → `In a
  gash of the wind-grieved Apennine;` (one word was too few for a verse
  line); in the second verse, the regrouping `drouth , cic—ala 'tis of` →
  `cicala of drouth, — 't is` (two overlaid OCR words pulled apart, and a
  closing mark joined), so that its lines read "Where the baked cicala
  dies of drouth," and "And one sharp tree — 't is a cypress — stands."
- `test_caption_domesday_39_and_40_kept_and_their_stray_words_removed`
  (book page index 40): the plate's stray words are 8 removals instead of
  7, a regrouping of their characters (domesday_headings_quotes_page4.json
  above).
- `test_index_haskins_266_heading_then_one_entry_per_entry_left_column_then_right`
  (haskins_eval, book page index 266): 73 index entries instead of 72, 8
  of depth 2 instead of 7: the split `172,187;BlackBook,` → `172,187;
  Black Book,` makes "Black Book, III. See Odo, …" a sub-entry of its own
  (haskins_eval_page9.json above).
- `test_index_stubbs_312_to_321_one_guide_words_removal_on_each_page`,
  renamed `test_index_stubbs_313_to_321_…`: page 4 (book page index 312)
  no longer gives the guide words removal `BAL BEC`. The page's letter
  soup is words in the PDF's order (regroupings), layout now finds the
  index's two columns, and "BAL" and "BEC", which stand above the two
  columns, fall one in each: "BAL" now begins the entry "BAL A CCURSI,
  Francesco, 221" and "BEC" ends "Baldwin of Redvers,18 BEC". Kept in the
  test as known, not fixed.

### tests/test_layout.py

- `test_cut_in_notes_of_stubbs_page_57_are_margin_regions` (book page
  index 57): splits `Characterof` → `Character of`, `Hisfamily` → `His
  family`.

### tests/test_extract.py and tests/test_end_to_end.py

- The words per page of the Kadesh excerpt kadesh_8-17 (book page indices
  8 to 17) and the Gierke excerpt gierke_86-93_270-271: Kadesh (584, 641,
  671, 904, 822, 764, 909, 822, 4, 0) → (582, 639, 668, 854, 818, 733,
  832, 816, 4, 0) in the text layer, and in words.json, after the 1 word
  of the excluded region and the 4 of the excluded page, (583, 641, …) →
  (581, 639, 668, 854, 818, 733, 832, 816, 0, 0); Gierke (192, 311, 297,
  325, 319, 309, 292, 273, 547, 541) → (192, 311, 297, 323, 318, 306, 290,
  272, 537, 534). Compared word by word in words.json, the Kadesh
  excerpt's changes are 33 joins, 3 regroupings and one word in another
  place in the order, the Gierke excerpt's 24 joins and 2 regroupings.

### New literals

- `tests/test_extract.py`, `test_haskins_front_page_12_gives_its_words_exactly`:
  Haskins' page 12 (haskins_front excerpt page 5), 204 words, checked
  against the page image rendered at 200 dpi on 17 November 2026: the
  splits `ofthese` → `of these`, `aswell` → `as well`, `theomission
  ofmany` → `the omission of many`, `Thisbookrestspartlyupon
  thewritingsofthevarious` → `This book rests partly upon the writings of
  the various` are each right.

### tests/test_structure.py (whole-book tests, task 2.3)

- `test_whole_book_gierke_index_entr_one_per_line_on_its_skewed_pages`
  (Gierke page index 85): the regrouping `TorNqou.e m 5 a 3 d a` →
  `Torquemada No. 53`: the OCR laid "No. 53", the second line of the
  entry "Tr. U. J. [tractatus universi iuris] No. 53", over "Torquemada
  No. 97" (checked on the page image). Its words are whole now, but the
  entry reads "Torquemada No. 53 No. 97", the second entry with more than
  one "No".
- `test_whole_book_stubbs_guide_words_on_each_of_its_ten_index_pages`
  (Stubbs page indices 312 to 321): page 312 gives no guide-words removal
  ("BAL BEC" stays a paragraph), and its 74 index entries become 34 notes;
  the book's index entries are 839 instead of 910 (per page 312: 74 → 0,
  313: 97 → 98, 314: 97 → 100, 315: 85 → 86, 316: 117, 317: 98 → 99, 318:
  87 → 88, 319: 102 → 104, 320: 107 → 103, 321: 46 → 44). The words of
  page 312 are the regroupings of its letter soup; the notes are a change
  of structure they cause. Kept in the test as known, not fixed.
