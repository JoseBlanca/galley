# The correct stage

The correct stage proposes fixes to the words the OCR misread, and writes
each fix as an edit that the markdown stage applies. It has a vision model
(a language model that reads images) read every text page of the book,
lines the model's words up with galley's words of the same page, and,
where two words that line up differ, proposes the model's word. It is
optional and off by default: `galley2epub run` runs it only when the
book's `book.toml` has `correct = true`.

Dated 19 November 2026. It builds what the measurement of the plan
notes-vision recommends, `docs/reports/notes-vision-measure.md` ("the
measurement" below): six pages of Kadesh (`battleofkadeshst00breauoft`),
transcribed by hand, against which each way of reading them was scored in
wrong words per 100 words of the transcription. On those six pages the
recommended way takes galley's notes from 26.5 wrong words in 100 to 3.4,
and the body from 2.0 to 0.7. Its cost is the **fluent wrong words**: a
wrong word that reads as a real word, so that nothing on the page shows it
is wrong, about 1 in 300 words (**Open 1**, at the end). Page means the
page index of the PDF, from 0.

No code of the stage exists: `src/galley/correct/__init__.py` is empty,
and markdown refuses any edit.

| reads | writes |
|---|---|
| the PDF, `pages.json`, `words.json`, `blocks.json`, the config | `edits/correct.jsonl` |

The architecture (`docs/architecture.md`) gives the book folder (section
5), the config (6), the formats (8), the edits (10) and the fidelity check
(13), the test that no word is lost or invented between a stage's input
and its output. This spec adds three config keys, a second version of the
edit's format, the stage `correct` to `book_folder.py`, and the rules by
which markdown applies an edit; the architecture is revised with it.

## 1. What it does

For each text page of the book, in parallel:

1. Render the page at 300 dpi, grayscale, and send the image to the vision
   model, through LM Studio, with the prompt of section 4. The model
   answers with the page's text, line by line.
2. Make galley's reading of the page: the words of the blocks and notes
   printed on it, from blocks.json, with the words the stage may not
   change marked fixed (section 5).
3. Line the model's words up with galley's, by least edits (section 7).
4. Where one of galley's words lines up with one of the model's and the
   two differ enough, propose the model's word in its place. In a note,
   where the model has words that line up with none of galley's, propose
   to put them in. Each proposal is an edit.

Then write the edits of every page, in page order, to
`edits/correct.jsonl`. markdown applies them before it writes `book.md`
(section 10). blocks.json stays as structure wrote it, and each edit can
be read and undone on its own (section 11).

The model's words are merged into galley's rather than taken whole
because the models drop note markers and print page numbers and running
heads as text, and Qwen 3.6 27B, reading the whole of Kadesh's page 29,
left out a map's caption of 13 words (the measurement, "The results").
Merging keeps galley's markers, its blocks and their order, and every
word the model does not read.

Words are put in only in the notes because in the body they added more
wrong words than right ones on the six pages (the measurement, "The
recommendation", point 3).

## 2. Terms

- **LM Studio**: the program on the owner's Mac that serves local
  language models over HTTP, at `http://localhost:1234` by default, with
  an interface like OpenAI's (`/v1/models`, `/v1/chat/completions`). Its
  command `lms` lists, loads and unloads models. It loads a model on the
  first request that names it.
- **The model**: the vision model that reads the pages, Qwen 3.6 35B-A3B
  by default, `qwen/qwen3.6-35b-a3b` in LM Studio.
- **galley's reading of a page**: the words of the blocks and notes
  printed on the page, as tokens, in the order of section 5.
- **A token**: a word as the alignment compares it: a piece of a text
  between white space and dashes, with its **comparison form** (section
  6). A token of galley's reading also knows where it is: its block, its
  span (a run of a block's text; a note reference is a span of its own)
  and the characters of its core in the span's text.
- **The core of a word**: the word without the ordinary punctuation at its
  ends and without a note marker glued to it (section 6): "struphes.”"
  has the core "struphes", "Greece,1" the core "Greece", "3%)" the core
  "3%". An edit changes a core and nothing around it.
- **A fixed token**: a token of galley's reading that the alignment uses
  but the stage never changes: a note marker, a note reference, a
  heading's label, a running head.
- **The footnote band**: the footnotes at the foot of a page (glossary);
  here, the strip of the page from 4 pt above the highest note block
  printed on it down to the bottom of the page.
- **Removals**: the words structure took out of the book on purpose, each
  with its page, box and reason, listed in blocks.json (architecture
  section 8): running heads, page numbers, signature marks (a printer's
  mark at the foot of some pages), figure text.

## 3. The config

Three keys, besides `correct` (architecture section 6). Each has a
default, so that a book needs none of them; they are checked whatever
`correct` is, and used only when the stage runs.

| key | type, default | meaning |
|---|---|---|
| `correct_model` | string, `"qwen/qwen3.6-35b-a3b"` | the model that reads the pages, as LM Studio names it |
| `correct_server` | string, `"http://localhost:1234"` | LM Studio's address: the scheme `http`, the host `localhost`, `127.0.0.1` or `[::1]`, any port, and no path, query or user. Anything else is a `ConfigError`, because a book's text, which may be under copyright, never leaves the machine (the plan: "a cloud model" is out) |
| `correct_second_model` | string, none | a second model, which reads each page's footnote band to mark the edits it disagrees with (section 9); none by default, since it marks but does not fix, and costs about 28 s a page |

## 4. Calling LM Studio

Every request goes to `correct_server`, over HTTP with the standard
library's `urllib`, and to no other host: not through a proxy, though the
environment names one (`http_proxy`, which `urllib` follows by default),
and not to the address of a redirect, which is an error.

**Before any page.** The stage asks `GET <server>/v1/models`, with a
timeout of 10 s, and checks that `correct_model` (and
`correct_second_model`, when given) is among the models listed. `cli.py`
makes the same check before the first stage of a command that runs
correct, so that `galley2epub run` stops before analyze rather than after
structure. Each failure is an `ExternalProgramError` whose message says
what to do:

- nothing answers at the address (the connection is refused, or 10 s
  pass): "LM Studio's server is not running at http://localhost:1234:
  start it in LM Studio or with `lms server start`";
- the model is not listed: "LM Studio has no model qwen/qwen3.6-35b-a3b:
  download it with `lms get qwen/qwen3.6-35b-a3b`", followed by the models
  it has;
- an answer that is not the JSON of a model list: the address and what
  came back, cut to 200 characters.

**A page.** One request, `POST <server>/v1/chat/completions`, with the
JSON body:

```json
{"model": "<correct_model>", "temperature": 0, "max_tokens": 6000,
 "reasoning_effort": "none",
 "messages": [{"role": "user", "content": [
   {"type": "text", "text": "<the prompt>"},
   {"type": "image_url", "image_url": {"url": "data:image/png;base64,<the page>"}}]}]}
```

The prompt, the one the measurement used:

> Transcribe the printed text in this image exactly as it is printed,
> line by line, in reading order. Do not correct spelling or wording, do
> not add anything, no commentary, no formatting. Skip hieroglyphs and
> drawings.

The page is rendered by `pdfium.render` at 300 dpi and sent as a
grayscale PNG. `reasoning_effort: "none"` turns the model's reasoning off:
on the notes of Kadesh's page 9 the 35B model took 4.3 s without it and
13.5 s with it, and LM Studio ignores the other ways of saying so (the
measurement, "For whoever builds the correct stage"). Temperature 0 makes
the answer as nearly the same on every run as LM Studio's arithmetic
allows; not checked across runs.

The model's text is `choices[0].message.content`. One request may take
600 s, guessed: the 35B model took 12.8 s a page on average on the six
pages, and the first request also waits for LM Studio to load the model's
20 GB, which was not timed.

- A refused connection, a timeout, an HTTP error status, or an answer
  without that field is an `ExternalProgramError` that names the page, the
  address, and LM Studio's own error message when it sent one. The stage
  stops and writes no edits file, so that a book is never half corrected.
- An answer cut short, `finish_reason` `"length"`, means the model ran on
  past 6,000 tokens, which on a page of about 600 words is a model
  repeating itself (page 11 took 1,409). The page gets no edits and the
  stage logs a warning that names it; the run goes on. Its text stays as
  galley read it, so nothing is lost, and the stage's last log line lists
  the pages it left so.

The stage does not load or unload models: LM Studio loads the model on the
first request and unloads it after its own idle time.

## 5. galley's reading of a page

The **text pages** are those whose kind in `pages.json` is `text`. A
plate, an excluded page, a front-matter or inkless page is never read
and never changed.

galley's reading of a text page is a sequence of tokens, in this order:

1. The **running head and page number** of the page, as fixed tokens: the
   words of blocks.json's removals of that page with the reason
   `running_head`, `page_number` or `signature_mark` whose box's middle is
   above the top of the page's highest block. The models print these as
   text; as fixed tokens they take the model's copy, which would otherwise
   pair with a word of the body.
2. The **body**: the blocks of blocks.json with an origin on the page,
   each with only its words printed on the page (below), ordered by the
   top of their box on the page, and by blocks.json's order when two tops
   are equal. blocks.json's order is not always the printed one: on page
   29 a map's caption, printed in the middle of the page, comes after the
   paragraph that surrounds it. In a block: a heading's or a contents
   entry's `label` first, then the spans, then an epigraph's `source` or
   a contents entry's `page_number`. The words of the label, the source,
   the page number and every note reference span are fixed. The words of
   the other spans are the ones the stage may change.
3. The **notes**: the notes with a block that has an origin on the page,
   in the order of blocks.json, each with its `group` and its `marker` as
   fixed tokens, then its blocks printed on the page, each as in step 2.
   On pages 11 and 15 this order is the order in which the model reads the
   notes, over both columns.
4. The removals of step 1 that are not above the highest block, as fixed
   tokens.

The other removals, figure text and a plate's stray text among them, are
not in the sequence: the models skip what is not text, and with them the
alignment would pair the model's words with junk.

**A block printed on two pages.** A paragraph that runs from page 12 to
page 13 is one block whose words are on both pages; on page 12 only those
printed there may be lined up with the model's reading of page 12. The
block's origin gives its box on each page. On each of its pages but the
last, the words of words.json of that page whose middle is in that box,
in rows from the top and from the left in a row (the rows of
`body_measures.group_rows`), are lined up by least edits (section 7) with
the block's tokens not yet placed, where the block's tokens after the
last one that pairs cost nothing to leave out. The block's tokens up to
that last paired one are its tokens on the page; the rest go to its next
page, and on its last page all the rest. Kadesh has 24 such body blocks
and 4 such note blocks among 175 blocks and 183 notes; on 26 of the 31
later pages of these blocks the split falls exactly where the page
begins, and on the other 5 one word later, the second half of a
hyphenated word or a word words.json lacks in that box.

## 6. The words compared

A text, the model's answer or a span's text, is cut into tokens:

1. In the model's answer only: markdown's asterisks, underscores, number
   signs, backquotes and bars, and anything between `<` and `>`, become
   spaces (the measurement's `score_vision.clean`); then a word broken by
   a hyphen at a line end is joined, without the hyphen, when the next
   line starts with a lower-case letter ("col-" and "lated" to
   "collated"), or when the part before the hyphen is in capitals and the
   next line starts with a capital ("MARI-" and "ETTE"). Not before any
   other line: the last body line of a page, "com-", is followed in the
   model's answer by the first note, "Called by…", and the measurement's
   rule, which joined before any letter or digit, made "comCalled".
2. The text is split at white space, and each piece at an em dash "—" or
   a double hyphen "--".
3. Each piece's core: the piece less the ordinary punctuation at its ends
   (`. , ; : ! ? ' " ( ) [ ]`, the curly quotes, "…"), then less a note
   marker glued after a word (any digits, "*", "†" or "‡" after two
   letters or more and any of that punctuation: "Greece,1", "Kadesh,12",
   but not "A1"), and less one to three digits, "*", "†" or "‡" glued
   before a capital and another letter ("3There"; not "1X", which is
   "IX" misread, and whose "1" a replacement would keep), then less the ordinary punctuation at its
   ends again. A core with no letter or digit, as "—" or "*", makes no
   token.
4. Its comparison form: Unicode NFC; curly quotes made straight; the
   ligatures ﬁ, ﬂ, ﬀ, æ and œ written out; accents and superscript
   digits dropped; every character that is not a letter or a digit at its
   ends dropped; hyphens and en dashes inside it dropped; case folded. Two
   tokens are equal when their comparison forms are.

This follows the measurement's normalisation (`common.tokens` in
`tmp/measure/` of the plan's worktree) except in three ways: the
line-end join of step 1; the core of step 3, which keeps characters such
as "%" that are no ordinary punctuation, since the OCR gives them for a
blurred digit ("3%" for a number of three digits); and the hyphens and en
dashes, which the measurement kept and the comparison drops, so that a
word that differs from the model's only by a hyphen is never edited
("temple-reliefs" and "templereliefs"). What follows from step 4: a word
that differs from the model's only in case, accents, quotes or a hyphen
is never edited ("Rougé" and "Rouge"), and the punctuation and glued
markers around a core are never edited.

## 7. The alignment, and the edits it gives

The model's tokens of a page are lined up with galley's reading of the
page by least edits: a pair of tokens costs 0 when equal, and when not 1
less a tenth of their **likeness**, the number of distinct characters
the two forms share over the number in the form that has more; a token
of either side left unpaired costs 1. Of alignments of equal cost, the
backtrace (from the end) takes a pair before an unpaired token of
galley's, and that before an unpaired token of the model's. This is the
measurement's alignment (its `common.align` without the wildcard) but for
the tenth, which only decides between alignments the measurement's costs
made equal: on a note "…is a puem." followed by the model's next note
number "15", unit costs pair "puem" with "15" as readily as with "poem",
and the likeness takes "poem". Since pairing two unequal tokens costs
less than leaving both unpaired, two tokens that stand at the same place
pair up whatever their letters.

From the pairs:

- **A replacement**: a pair whose tokens differ, whose galley token is not
  fixed, and whose comparison forms are at least 0.3 alike by difflib's
  `SequenceMatcher.ratio`: the pairs that a word out of place makes,
  "Kadesh" with "city" on page 27, are 0; "puem" and "poem" are 0.75,
  "ia" and "in" 0.5, "3%" and "305" 0.5. Measured on the six pages with
  the measurement's recorded answers, 19 November 2026: without the
  limit the notes come to 3.8 wrong words in 100 and the edits bring 14
  fluent wrong words; with 0.3, 5.3 and 11 ("Borchardt" for "Brugsch"
  twice and "Med." for "Hist." no longer); with 0.5, 6.7 and 8. 0.3 is
  kept, since a fluent wrong word costs the reader more than a visible
  one (**Open 1**). The model's core replaces galley's core in the span, and the
  punctuation and any glued marker around galley's core stay. One rule
  touches the model's word: the models write small capitals as capitals,
  "MASPERO's" where galley has "Masrvuo's". When the model's core, less a
  final "'s", has no lower-case letter, galley's core has one, and the
  model's is not a roman numeral (only the letters I, V, X, L, C, D, M),
  the model's core takes galley's case: a capital first and the rest
  lower when galley's core starts with a capital, all lower otherwise.
  So "Masrvuo's" becomes "Maspero's". The measurement's scoring folds
  case, so this rule changes none of its numbers.

  A pair that may hold more printed words on galley's side than on the
  model's gives no replacement, since replacing it would lose a word
  (review of 19 November 2026: about 40 such edits in the Kadesh run,
  "542,543.)" made "543.)", "fiveminutes." made "minutes.", "12-18)."
  made "18)."). That is when galley's core has (a) more commas, full stops,
  colons, hyphens or en dashes between two letters or digits than the model's
  core; or (b) more digits than the model's core and two digits side by
  side (a lone digit is often a letter misread, "a3" for "as", "V1" for
  "VI", which stay fixable). Junk inside a word is not such a mark:
  "maje=ty," still becomes "majesty,".

  **Two printed words galley glued.** When galley's core has more letters
  and digits than the model's paired token, and that token joined with
  the unpaired model token just before or just after it is more alike
  galley's form than the token alone, galley glued the two printed words
  the model reads apart: galley's core is replaced by the model's text
  from the first token's core to the second's, with what stands between
  them ("fiveminutes." becomes "five minutes.", "tothe" "to the"), and
  the unpaired token is not put in elsewhere. This is checked before (a)
  and (b), and then (a) holds for the two words with the space between
  them counted as one more mark: "1l.1.2.and", three marks, does not
  become "2, and", which would lose "1l.1." (the second Kadesh run, 19
  November 2026, page 47; and "7:3" became "35" on page 33 before the
  colon was a mark). Measured with the recorded answers on the six pages, 19
  November 2026: refusing such pairs, as (a) and (b) do, took the notes
  from 5.3 wrong words in 100 to 6.3, since "tothe" stayed where "the" had
  been put; taking both words brings them back to 5.3, with no word lost.
- **A block whose words are out of place.** When galley's reading of a
  block on a page is in another order than the model's, the alignment
  pairs words that have nothing to do with each other, and each such pair
  can pass the 0.3 limit by chance between short words ("his" with
  "Mashawasha", 0.31). Such a block part shows it in the mean likeness of
  its unequal pairs: on Kadesh's page 14, from the notes' blocks
  b-p0014-005 to b-p0014-011, 0.00 to 0.19; on the six pages of the
  measurement, 0.36 to 0.93 but for one block of page 27 at 0.22, whose
  six pairs are the rotated "Kadesh" with "city" (measured with the
  recorded answers, 19 November 2026). So when a block's unequal pairs on
  a page are 3 or more and their mean likeness is below 0.3, the stage
  makes no edit in that block on that page, neither replacement nor
  insertion, and logs it.
- **An insertion**: a run of the model's tokens that pair with none of
  galley's, inside a note: the galley token before the run is a token of
  the note (its marker or a word of its blocks), and the one after is a
  token of the same note, or the marker or first token of the next note.
  The run's tokens that are only digits are left out of it: they are the
  notes' own numbers, which the model prints and galley holds as markers
  (83 of Kadesh's 183 note markers give no token, empty or "*" or "%"),
  and the page number the model prints between two note columns. The
  run's other words, joined by one space, go into the note: after
  galley's token just before the run when the stage may change it; when
  it is fixed (the run comes right after the marker or a note reference),
  before the first word after the run that the stage may change, in the
  same note, or else after the last such word before the run, in the same
  note. The run goes after or before the whole word, with its
  punctuation: "the." and "Bulletin" give "the. Bulletin". When the note
  has no word the stage may change, the run is not put in, and the stage
  logs it. A run of two words or more that galley's reading of the page
  already holds, the same words one after the other, is not put in: it is
  the model reading a line twice or the alignment placing a line of
  another block there (page 32 "Read the above is a typographical error"
  in its note twice; page 51 words of the body put into note 132). A run
  elsewhere, in the body, before the page's first token or after its
  last, is not put in: there it is page numbers and running heads.
- A pair with a fixed token, a pair less alike than 0.3, a pair that may
  hold more words on galley's side, a pair in a block whose words are out
  of place, and a galley token paired with nothing, give nothing:
  galley's word stays.

What the stage never changes, whatever the model reads: a note marker, a
note reference, a heading's label, an epigraph's source, a contents
entry's page number, a running head or page number, the order of blocks
and notes, the words of any page that is not a text page, and every word
the model does not read.

## 8. The edits it writes

`edits/correct.jsonl` holds the edits, one per line, in page order, and on
a page in the order of galley's reading. The edit's format goes to version
2 (architecture section 8): it gains three fields, which an edit made by a
person or an agent writes as `null`. Only version 2 is read; no file of
version 1 exists, since markdown refused every edit until now.

| field | for an edit of correct |
|---|---|
| `format_version` | 2 |
| `block_id` | the block of the changed span; for a note, the id of the note's block |
| `block_sha256` | of the block's text as structure wrote it |
| `old` | the word that holds the changed core, with the words around it that make it occur once (below) |
| `new` | `old` with the model's core in place of galley's, or with the inserted words |
| `author` | `"correct"` |
| `reason` | `"vision_word"` for a replacement, `"vision_missing_words"` for an insertion |
| `page_index` | new: the page the word is printed on |
| `model` | new: `correct_model` |
| `second_reading` | new: the second model's reading at the same place (section 9), or `null` when there was no second reading or the edit is not in a note |

One edit for each replacement and each insertion. For a replacement,
`old` is the whitespace word of the span that holds the core; for an
insertion, the word the run goes after or before, and `new` that word
and the run, separated by one space. When `old` occurs more than once in
the block's text, neighbouring words of the same span are added, one at
a time and alternately, the next word after, then the next before (only
the other side once one side reaches the span's edge, or a word another
edit changes), until it occurs once both in the block's
text as structure wrote it and as the stage's earlier edits of the block
leave it. A neighbouring word that another edit of the stage changes is
never added, so that each edit applies whether or not the others do, and
deleting one line undoes one edit. When no such context makes `old` occur
once, the change is not proposed and the stage logs it, with its page and
block.

The model gives no confidence for a word that the stage could record:
LM Studio's answer holds the text only. The second reading is the
stage's measure of doubt.

The stage deletes `edits/correct.jsonl`, `book.md` and `book.epub` before
it reads its inputs, as every stage deletes its own file and those of the
stages after it (architecture section 5). structure, and every stage
before it, also deletes `edits/correct.jsonl`, since its edits name
blocks by their text as structure wrote it. `book_folder.Stage` gains
`correct`, between structure and markdown, with that file. No other file
under `edits/` is ever deleted or written by a stage.

## 9. The second reading

When `correct_second_model` is given, the stage also sends each text page
that has notes to that model, the image cut to the footnote band, with
the same prompt and request; the measurement recommends Qwen 3.6 27B
(`qwen/qwen3.6-27b`). The second model's tokens are lined up, as in
section 7, with the notes' part of galley's reading of the page (step 3
of section 5, fixed tokens included). For each edit in a note:

- a replacement: `second_reading` is the second model's core paired with
  the same galley token, or `""` when none pairs with it;
- an insertion: the second model's tokens that pair with none of galley's
  between the same two galley tokens, digits left out as in section 7,
  their cores joined by one space, or `""`.

An edit is **doubtful** when its `second_reading`, in comparison form,
differs from its new words. The stage does not drop a doubtful edit: it
logs how many there are, and the owner decides (section 11). What the
measurement found is for a nearby setup only: with both models reading
the footnote bands, Qwen 3.6 27B read differently 24 of the 35B model's 33
wrong note words and 9 of its 1,330 right ones. For this stage, where the
35B model reads whole pages, the measurement's recorded answers give on
the six pages 345 note edits, of which 21 wrong: the second reading
makes doubtful 18 of the 21 and 27 of the 324 right ones, 45 edits to
check (an edit counted right when its words are words of the reference
at that place). The second reading costs about 28 s a page on the
owner's Mac, about 20 minutes for Kadesh's 43 pages with notes.

## 10. How markdown applies the edits

markdown reads every `*.jsonl` file under `edits/`, `correct.jsonl`
first, then the others by file name, then `owner.jsonl` last
(architecture section 10), and applies each file's edits from its first
line to its last, to the blocks of blocks.json, before it writes
`book.md`. It applies whatever files are there: the config's `correct`
decides whether `run` runs the correct stage, not whether its file is
read.

An edit applies when:

1. its block is among blocks.json's blocks and its notes' blocks;
2. `block_sha256` is that of the block's text as structure wrote it;
3. `old` occurs exactly once in the block's text as edited so far; and
4. that occurrence lies inside one span that is not a note reference.

Then `old` is replaced by `new` in that span. The other spans, the
block's label, source and page number, and the note's marker are not
touched. Rule 4 is new with this spec: it keeps an edit, by any author,
from changing a note reference or joining two spans.

An edit that does not apply is not skipped: markdown tries every edit,
then stops with an `EditError` that lists each one that did not apply,
with its file, line and the rule it broke. The fidelity check of the
markdown boundary (architecture section 13) compares the blocks with the
edits applied against `book.md`, as it already says. markdown logs how
many edits of each file it applied.

## 11. How the owner sees and undoes the edits

The owner proofreads `book.md`, which holds the corrected text, and
`edits/correct.jsonl`, one edit a line, with its page, block, old and new
words and, with a second reading, what the second model read: a doubtful
edit is one whose `second_reading` is neither `null` nor its new word.
Nothing in `book.md` or the EPUB marks a corrected word: a mark would
show in the EPUB.

- To undo one edit: delete its line from `edits/correct.jsonl` and run
  `galley2epub markdown` and `epub` again. It holds until correct runs
  again and rewrites the file.
- To reject it for good: write the old word back in the owner's own
  edits, `edits/owner.jsonl`, which apply after correct's; by hand until
  `galley2epub edits-from` is built.
- To undo them all: delete the file, or set `correct = false` and run
  `galley2epub run`.

The owner's edits made on corrected text depend on correct's: when correct
is turned off or reads a word differently on a later run, such an edit may
no longer apply, and markdown stops and lists it (section 10), as it does
when structure changes.

On the whole of Kadesh, run on 19 November 2026 with the 35B model, the
stage made 1,218 edits on its 44 text pages in 474 s (the Mac shared with
other work; about 11 s a page), and markdown applied all of them. On the
six pages of the measurement those edits take galley's reading from 2.7
wrong words in 100 to 1.3 in the body and from 26.8 to 5.5 in the notes,
and bring 11 fluent wrong words among 3,331 words ("orientalis" for
"orientalists" twice, "Rev." for "Rec." twice, "Egyptian" for the
misprint "Eygptian"); at that rate about 37 in the book, too many to
find by reading, which is why the stage is off by default (**Open 1**).

## 12. The public interface

The stage's entry point, as every stage's (architecture section 9):

```python
def run(folder: BookFolder, config: BookConfig, *, workers: int = DEFAULT_WORKERS) -> None:
    """Write edits/correct.jsonl: the vision model's fixes to galley's words
    of every text page, as edits. Raises ExternalProgramError when LM Studio
    does not answer or lacks the model, InputFileError for stale inputs."""
```

The check `cli.py` makes before any stage when a command runs correct:

```python
def check_server(config: BookConfig) -> None:
    """ExternalProgramError when LM Studio's server at config.correct_server
    does not answer, or does not list config.correct_model or, when given,
    config.correct_second_model among its models."""
```

The command: `galley2epub correct <book folder>` runs the stage whatever
`correct` says; `galley2epub run <book folder>` runs it between structure
and markdown when `correct = true`.

markdown gains `apply_edits(blocks, edits) -> BlocksFile`, the blocks with
the edits applied by section 10, where `edits` holds each edit with its
file and line; it raises `EditError` as section 10 says.

## 13. How it runs in parallel

Over pages, with `parallel.map_pages`: each worker renders its page
through `pdfium.render` (which runs PDFium in its own thread), makes the
PNG with Pillow, sends the request and waits, then makes the page's edits
from the model's answer and galley's reading, a pure function. A page
needs nothing from another page but the split of a block printed on two
pages (section 5), which is made before the workers start, from
blocks.json and words.json. The context of an `old` (section 8) is chosen
after the workers, over each block's edits from all its pages. The edits
are gathered in page order, so the file is the same whatever the number
of workers, as long as the model's answers are. LM Studio answers several
requests at once or one after the other, as its settings say; the workers
wait either way.

## 14. Cases

- **Kadesh page 11.** galley's note reads "Masrvuo's statement (Struggle,
  p. 3%) that it is “a puem ia rhymed struphes.”"; the model's whole-page
  answer "MASPERO's statement (Struggle, p. 305) that it is "a poem in
  rhymed strophes,"". The edits replace "Masrvuo's" by "Maspero's", "3%)"
  by "305)", "puem" by "poem", "ia" by "in" and "struphes.”" by
  "strophes.”", keeping galley's curly quotes and full stop. The
  citation's page number is too blurred for the measurement's reference
  to read; the 35B model read "305" on the whole page and "395" on the
  footnote band alone, so one of its readings is a fluent wrong word.
- **A note's marker misread.** galley's marker "%" of the note "Called by
  de Rougé the Bulletin." stays, whatever the model reads there: a marker
  is fixed. The model's number "15" before the note, which pairs with
  nothing, is digits and is not put in.
- **A glued marker.** A note reference structure did not split off,
  "Kadcsh,12", has the core "Kadcsh"; the model's "Kadesh" gives the edit
  "Kadcsh,12" to "Kadesh,12". A reference structure did split off is a
  span of its own, and fixed.
- **A running head.** The model prints "6" and "THE BATTLE OF KADESH" at
  the top of page 11, where galley's reading has the removed running head
  "} Tur BatTLe or KapEsH#" as fixed tokens; they pair, and no edit is
  made.
- **A word hyphenated over a page break.** "com-" at the foot of page 10's
  body is not joined to the first note of the model's answer.
- **The hieroglyph rows of page 27.** The words galley read inside the
  figures are removals, not in its reading; the model skips them; nothing
  pairs.
- **A word the model drops**, a note marker in the body or a map's
  caption: galley's word pairs with nothing and stays.
- **A plate page** is not read.

## 15. How it is verified

- **Unit tests**, with recorded answers and never a model. The first
  asserts the tokens of literal words: "struphes.”" has the core
  "struphes", "Greece,1" the core "Greece", "3%)" the core "3%", "—" no
  token, and "Rougé" and "ROUGE" one comparison form. Then: the alignment
  on literal token lists; the edits of Kadesh page 11 from galley's
  reading of it and the 35B model's recorded answer
  (`tests/fixtures/correct/`), against the edits of section 14 written as
  literals; the note numbers and page number of pages 9 and 15 not put
  in; an insertion in a note and none in the body; a word that occurs
  twice in its block; a block printed on two pages; the second reading's
  values; markdown's four rules, each broken in a case of its own, with
  the file and line in the error; the config's three keys with values
  other than their defaults, and an address that is not local refused.
- **The calls**, with a small HTTP server inside the test, on localhost,
  that answers with recorded answers: the request's body; the
  `ExternalProgramError` when nothing listens on the port, when the model
  is not listed, on an HTTP error status; and the warning on an answer
  cut short.
- **An excerpt test**: the stage on the excerpt `kadesh_redo` (whole-book
  pages 8 to 16, 32 and 34; Kadesh's page 11 is its page 3), with the
  test's server answering for each page the 35B model's answer, recorded
  once for every page of the excerpt under `tests/fixtures/correct/`; the
  edits file is the same with 1 worker and with 8, and markdown applies
  it and passes the fidelity check.
- **One test marked `vision_model`**, excluded by default as `whole_book`
  is, that calls LM Studio with the 35B model on page 3 of the excerpt
  `kadesh_redo` and checks that the edits turn "puem" into "poem" and
  "Masrvuo's" into "Maspero's", and that no edit holds a note reference.
- **Kadesh**, by hand, at the end of work package 4: the whole book with
  `correct = true`; on the six pages of the measurement, galley's reading
  of each page (section 5) with the edits applied, scored against the
  measurement's reference (`tmp/measure/ref/`) by its own scoring, body
  and notes apart, its fluent wrong words counted, against its 0.7 and
  3.4 and against galley's reading without the edits; the share of wrong
  note edits the second reading would flag, from the recorded 27B
  answers; and the time for the book.

## 16. Open points

1. **Whether a fluent wrong word in about 300 is acceptable**, against
   about 3 wrong words in 10 in Kadesh's blurred notes today. The options:
   (a) the stage as specified, off by default, and `correct = true` for
   Kadesh only, every edit in `edits/correct.jsonl`: 1,218 edits, about 37
   of them fluent wrong words (estimated from the six pages), none
   flagged; (b) the same with the second reading on, for about 20 more
   minutes a run: on the six pages it flags 18 of the 21 wrong note edits
   and 27 of the 324 right ones, so the owner checks about 1 edit in 8,
   some 150 for the book (estimated), and the body's edits stay
   unflagged; (c) the stage not used. Recommended: (b) for Kadesh, (c) for
   a book whose OCR is good, until the stage is measured on a second
   book. Meanwhile the stage is off by default and
   every edit is in its file.

## 17. Not in this spec

- `galley2epub edits-from`, by which the owner writes edits from a
  corrected copy of `book.md`: part of the markdown spec, not written.
- Reading only the footnote bands with the main model, which the
  measurement found cheaper when the body is already good: not built.
- Another prompt, resolution or model: one prompt and 300 dpi were
  measured.
- How the stage does on books other than Kadesh: not measured.
