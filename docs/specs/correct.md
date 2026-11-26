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
is wrong, about 1 in 300 words (section 16). Page means the
page index of the PDF, from 0.

No code of the stage exists: `src/galley/correct/__init__.py` is empty,
and markdown refuses any edit.

| reads | writes |
|---|---|
| the PDF, `pages.json`, `words.json`, `blocks.json`, the config, the model's kept answers under `answers/` | `edits/correct.jsonl`, and an answer under `answers/` for each request it sends (section 4b) |

The architecture (`docs/architecture.md`) gives the book folder (section
5), the config (6), the formats (8), the edits (10) and the fidelity check
(13), the test that no word is lost or invented between a stage's input
and its output. This spec adds four config keys, a second version of the
edit's format, the stage `correct` to `book_folder.py`, and the rules by
which markdown applies an edit; and, on 25 November 2026, the folder
`answers/` and the format of a kept answer (section 4b). The
architecture is revised with it.

## 1. What it does

For each text page of the book, in parallel:

1. Render the page at 300 dpi, grayscale, and send the image to the vision
   model, through LM Studio, with the prompt of section 4. The model
   answers with the page's text, line by line. An answer kept from an
   earlier run to the same request is read from the book folder instead
   (section 4b).
2. Make galley's reading of the page: the words of the blocks and notes
   printed on it, from blocks.json, with the words the stage may not
   change marked fixed (section 5).
3. Line the model's words up with galley's, by least edits (section 7).
4. Where one of galley's words lines up with one of the model's and the
   two differ enough, propose the model's word in its place. In a note,
   where the model has words that line up with none of galley's, propose
   to put them in. Each proposal is an edit.
5. When `correct_links` is true (the default), on a page where a footnote starts, send the page a second time, with the
   prompt of section 9b, which asks for the text with each note
   reference marked; where the model marks a reference after a word of
   galley's and names one of the page's notes, propose a link from that
   word to that note (section 9b). Each link is an edit too.

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

Four keys, besides `correct` (architecture section 6). Each has a
default, so that a book needs none of them; they are checked whatever
`correct` is, and used only when the stage runs.

| key | type, default | meaning |
|---|---|---|
| `correct_model` | string, `"qwen/qwen3.6-35b-a3b"` | the model that reads the pages, as LM Studio names it |
| `correct_server` | string, `"http://localhost:1234"` | LM Studio's address: the scheme `http`, the host `localhost`, `127.0.0.1` or `[::1]`, any port, and no path, query or user. Anything else is a `ConfigError`, because a book's text, which may be under copyright, never leaves the machine (the plan: "a cloud model" is out) |
| `correct_links` | bool, `true` | whether the stage also proposes note links (section 9b), at the cost of a second request on each page where a footnote starts; on by default since 40 links on whole Kadesh were all right (section 9b, "Measured") |
| `correct_second_model` | string, none | a second model, which reads each page's footnote band to mark the edits it disagrees with (section 9); none by default, since it marks but does not fix, and costs about 28 s a page |

## 4. Calling LM Studio

Every request goes to `correct_server`, over HTTP with the standard
library's `urllib`, and to no other host: not through a proxy, though the
environment names one (`http_proxy`, which `urllib` follows by default),
and not to the address of a redirect, which is an error.

**Before the first request.** The stage asks `GET <server>/v1/models`,
with a timeout of 10 s, and checks that `correct_model` (and
`correct_second_model`, when given) is among the models listed. It does
so once in a run, just before the first request it actually sends, and
not at all when every answer it needs is kept (section 4b), so that a
book is rebuilt from its kept answers with LM Studio stopped. `cli.py`
makes the same check before the first stage of a command that runs
correct when the book folder has no `answers/` yet, so that a first
`galley2epub run` stops before analyze rather than after structure; when
`answers/` exists, it leaves the check to the stage, which may need no
model. Each failure is an `ExternalProgramError` whose message says
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

## 4b. The kept answers

Added on 25 November 2026 for the plan misread-words
(`docs/plans/misread-words.md`, work package 1). The stage keeps every
answer the model gives in the book folder, and a later run that would
send the same request reads the answer there instead of asking the model.
The model takes about 11 s a page with the 35B model (sections 11 and
16), 1 to 3 hours for a whole book; with the answers kept, the merge's
rules can be changed and measured again on whole books, and a book
rebuilt after structure ran again, at the cost of rendering the pages
and merging. Rendering a page at 300 dpi and making its PNG took 0.15 s
on average over the ten pages of the excerpt `kadesh_redo`, one thread,
on the owner's M5 Pro (25 November 2026).

**Where.** One JSON file for each request, in `answers/` of the book
folder, named `<kind>-<page index, 4 digits>.json`: the kind `page` for
the reading of the page (section 1, step 1), `band` for the second
reading of its footnote band (section 9) and `links` for the reading
with the note references marked (section 9b). Kadesh's page 11 has
`answers/page-0011.json`, `answers/band-0011.json` and
`answers/links-0011.json`.

**What a file holds** (architecture section 8, the kept answer):

| field | what it is |
|---|---|
| `format_version` | 1 |
| `page_index` | the page, an integer |
| `kind` | `page`, `band` or `links` |
| `model` | the model that answered |
| `prompt` | the prompt it was sent |
| `image_sha256` | the SHA-256 of the PNG it was sent, in hex |
| `request_sha256` | the SHA-256, in hex, of the bytes of the request's body as section 4 gives it, the image in it |
| `text` | the model's text, `choices[0].message.content` |
| `cut_short` | true when the answer was cut short, `finish_reason` `"length"`; false otherwise |

Only `request_sha256` decides whether the answer is used. The model,
prompt, image digest, page and kind are there for a person, or a tool
such as the plan's `galley-eval edits`, to read, and are not checked
against the file's name or the request; a `text` corrected by hand is
used as it stands.

**When an answer is used.** For each request, the stage first makes the
body it would send, as JSON with its keys sorted, so that the order they
are written in the code does not count, no space after a comma or colon,
and the characters as they are (not escaped), in UTF-8; it sends exactly
these bytes, and computes their SHA-256. When the request's file exists and holds that `request_sha256`,
the stage takes its `text` and `cut_short` and sends nothing. Otherwise
it sends the request, as section 4 says, and writes the answer to the
file, in place of the one there. So anything that changes what is sent
asks the model again: another model or prompt, another temperature,
`max_tokens` or `reasoning_effort`, a field added to the body, and
another image, as when structure moved a note and with it the top of the
footnote band, or a new version of PDFium or Pillow renders or encodes
the page otherwise (then every page is asked again). The server's address
is not in the body and does not count. The page is rendered on every
run, since its image is part of the request.

**A request that fails, or an answer cut short.** A request that fails
(a refused connection, a timeout, an HTTP error status, an answer
without its text) keeps nothing, and the stage stops as section 4 says;
the answers already written stay, so the next run asks only for the
rest. An answer cut short is kept, with `cut_short` true, and the next
run uses it as such: the page again gets no edits (or no links) and the
warning of section 4. Asked again at temperature 0, the model would most
likely run on to 6,000 tokens again, the longest request the stage
makes. To have the page read again, delete its file.

**Written whole.** Each file is written to a temporary file beside it,
`.<name>.<process id>.<thread id>.tmp`, then moved over it, so that a
run stopped at any moment leaves the old answer, the new one, or none,
never part of one. A temporary file a killed run leaves is never read
and may be deleted.

**A file that cannot be read** — not UTF-8, not JSON, of another
`format_version`, or with a field missing, unknown or of the wrong type —
is an `InputFileError` that names the file and says to delete it, and
the stage stops without writing `edits/correct.jsonl`. It is not taken
for a missing answer: since the stage writes every file whole, such a
file was made by something else, a hand edit or a damaged disk, and
asking the model again in silence would hide that.

**Never deleted by a stage.** An answer depends only on the request,
and the request only on the config and the image (for the footnote band,
cut where blocks.json's highest note on the page starts), so no file of
another stage can make an answer stale without changing the request's
SHA-256.
`book_folder.delete_stage_outputs` never touches `answers/`, and
`galley2epub run` keeps it whatever stages it runs. A file of a page that
is no longer a text page, or of a kind no longer asked for (`correct_links`
false, no `correct_second_model`), stays and is not read. To have the
model read every page again, delete `answers/`.

**Threads.** A file is read and written only by the worker that has its
page, so no two threads touch one file; `answers/` is made before the
workers start. The check of the server (section 4) is made under a lock
by the first worker about to send a request; the others that are about
to send one wait for it, and none checks again once it passed. When it
fails, the stage stops with its error. Rendering stays in PDFium's thread
(section 13).

The stage's last log line says how many answers it read from
`answers/` and how many it asked the model for.

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
  one (section 16). The model's core replaces galley's core in the span, and the
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
  "VI", which stay fixable); or (c) a piece of digits and marker signs
  ("*", "†", "‡", "%") glued before or after two letters or more, which the
  model's core does not hold: a note marker misread, as in "1%The" on
  Kadesh's page 53, which became "The" in the third run of 19 November
  2026 because its one digit escaped (b). The piece is two characters
  or more, or holds a sign: one digit alone is often a letter misread
  ("1bid" for "ibid", "4meni" for "Ameni" on the excerpt `kadesh_redo`),
  and stays fixable. Junk inside a word is not such a mark:
  "maje=ty," still becomes "majesty,".

  **Two printed words galley glued.** When galley's core has more letters
  and digits than the model's paired token, and that token joined with
  the unpaired model token just before or just after it is more alike
  galley's form than the token alone, galley glued the two printed words
  the model reads apart: galley's core is replaced by the model's text
  from the first token's core to the second's, with what stands between
  them ("fiveminutes." becomes "five minutes.", "tothe" "to the"), and
  the unpaired token is not put in elsewhere; a line break of the model's
  between them is one space, or nothing after a hyphen ("non-" and
  "Libyan" give "non-Libyan"). This is checked before (a)
  and (b), and then (a) holds for the two words with the space between
  them counted as one more mark: "1l.1.2.and", three marks, does not
  become "2, and", which would lose "1l.1." (the second Kadesh run, 19
  November 2026, page 47; and "7:3" became "35" on page 33 before the
  colon was a mark). Measured with the recorded answers on the six pages, 19
  November 2026: refusing such pairs, as (a) and (b) do, took the notes
  from 5.3 wrong words in 100 to 6.3, since "tothe" stayed where "the" had
  been put; taking both words brings them back to 5.3, with no word lost.

  Such a split is refused, as a replacement of one token would be, when
  it would lose what galley read (review of 26 November 2026, on the
  whole-book reruns): when the model's two tokens joined, letters and
  digits alone, are shorter than galley's form and its start or its end
  (Domesday's margin note "towitesand" became "wites and", losing "to";
  Stubbs' "andadventurous," became "and adventu-,"); when a digit of
  galley's core is not kept, in order, among the joined tokens' digits,
  which is (b) for the pair (Domesday's table row "909" became "0 9",
  six such rows; "1800" became "140 360", numbers of other rows;
  "4v=120A" became "V = 120"); and when the model's first token ends in
  a hyphen and the two joined are not galley's form, a line-end half
  the answer did not join (Stubbs' "discontented" became
  "discon-Henry"). A hyphen whose join is galley's word stays allowed:
  "nonLibyan" against "non-" and "Libyan" gives "non-Libyan". Nor is
  it made when the model's tokens joined hold three letters or more
  than galley's form and a token of galley's reading of the page shares
  with them a run of four characters or more that galley's form lacks:
  galley holds the second half of a word broken at a line end
  elsewhere, where layout placed it beside a margin note, alone or
  glued to the next word, and the split would print that half twice
  (Stubbs' page 72: galley's "howfind" became "however, find" while
  galley's "ever," stayed further on; page 202, "marand" became
  "marriage and" beside galley's "augriage"). The four characters are
  guessed, not measured. No right judged split on the seven sheets adds a letter.

  When galley glued three words or more, the split takes the model's
  unpaired tokens after the two, then before them, as long as all of
  them joined are the start, or the end, of galley's form: Gierke's
  "nature~~of~an" becomes "nature of an" rather than "nature of", which
  lost "an", and Domesday's "towitesand" becomes "to wites and". A
  refused split's tokens, and the unpaired ones beside them that
  galley's form holds, are not put in elsewhere: Domesday's
  "4v=120A." against "V = 120. A" kept the "4" but had "A" put in after
  it.

  A word galley holds twice or more in its text of the book is
  not split so: it is a word, printed as galley reads it, and the model
  read a gap in it or the end of a line. On Stubbs' page 291 the model's
  "of" and "tained" for the printed "ob-" and "tained" split "obtained",
  printed 22 times in the book, into "of tained"; on Domesday's page 99
  "Ælfric", read by galley as "^Elfric" six times, became "Ælf ric".
  Measured on the seven judged sheets (26 November 2026): of the 17
  judged splits of one of galley's words into two, 4 are wrong, and the
  rule takes 2 of the 4, these two, whose word galley holds more than
  once. The other two wrong ones are of words galley holds once and
  stay: Domesday's "haula," to "haul a," and "680A." to "H.=680. A".
  Each of the 13 right ones is of a word galley holds once: glued words
  ("thedeterminative", "shouldbe"), a number glued to what follows it
  ("220f.)" to "220 f.)", "1.7" to "1. 7"), and junk or a hyphen read
  between two words ("by^Ockhatn." to "by Ockham.", "act-of" to "act
  of"). The limit was three until the review of 26 November 2026 found
  Domesday's "Brungar" split into "Brun gar" and Stubbs' "Geddington"
  into "Gedding ton", each held twice; at two the judged splits give
  the same counts.

  A split into pieces that are each a word of the list, digits or a
  form galley's text holds was measured and is not a rule: it takes 1
  of the 4 wrong judged splits and none of the 13 right ones, but on
  the excerpt `kadesh_redo`, whose ten pages hold few forms, it refuses
  5 right splits of its 469 edits ("Golénischeff'stext", "n.s.",
  "1,300,520,"). Domesday's "Wulfsige" to "Wulf sige", "Wulfsige" held
  once, and "haula," to "haul a," stay.

  **A word galley left split at a line end.** structure joins a word
  hyphenated at a line end only when the joined word is known, so a
  misread half stays as printed, "cam- P#@igns" on Kadesh's page 8, while
  the model's answer, joined by section 6, holds "campaigns". When
  galley's word is the second half of such a word, the replacement
  covers both halves. That is when the whitespace word just before it in
  the same span ends in a letter and a hyphen (or "¬"), the last token of
  that word is the token just before in galley's reading of the page,
  that token pairs with none of the model's, and the two forms joined
  are more alike the model's form than galley's form alone. Then the
  model's core replaces the text from the first half's core to the
  second's, the hyphen and the space between them included: "cam-
  P#@igns" becomes "campaigns", where the first run of 19 November 2026
  replaced the second half alone and left "cam- campaigns". (a), (b) and
  (c) are checked on the two cores joined without the hyphen and the
  space. The model's word decides what becomes of galley's hyphen:

  - the model printed the word broken at a line end before a lower-case
    letter ("cam-" and "paigns"): the hyphen goes, "campaigns";
  - it printed it broken at a line end with both halves in capitals
    ("DINDORF-" and "MÜLLER", page 61): the hyphen stays, and each half
    takes the case of galley's half, so "Dirporr- MCiuer," becomes
    "Dindorf-Müller,". Section 6 joins such halves without the hyphen
    for comparing, since in capitals a line-end hyphen may be the
    printer's ("MARI-" and "ETTE") or the word's; here, where galley also
    has the hyphen, it is kept (review of 19 November 2026, which found
    "Dindorfmüller,");
  - it printed the word whole, with no line end inside: no edit, since
    galley's hyphen may be the word's own.

  The run of 19 November 2026 has 3 such edits among its 1,050
  ("cam- P#@igns" on page 8, "Dirporr- MCiuer," on page 61, and
  "com- (Newaey." on page 11, whose first half is on page 10 and which
  the rule leaves alone). A first half that the model's whole word pairs
  with, "Erldu-" with "Erläuterungen" on page 20, is not covered: there
  galley's second half, "Sees...", may also hold the printed "etc.",
  which a replacement of both halves would lose.
- **Two of galley's words for one printed word.** When galley's token
  pairs with the model's, the token just before or just after it in the
  same span pairs with none of the model's, only white space stands
  between their cores, and either the two forms joined are the model's
  form or each of the two is one character and the model's form two,
  the replacement covers both: the model's core replaces the text from
  the first core to the second, the space between them included. (a)
  and (b) are checked on the two cores joined without the space.
  structure split one printed word in two, at a gap between its letters
  or at a broken letter, and the model read it whole. On Domesday's page
  29 (`domesdaybook00maituoft`, the trial of 25 November 2026) the page
  prints "It," where galley has "I i,"; the model's "It" replaced the
  second token alone and the page read "I It,". On Haskins' book galley
  has "11 56" for the printed year 1156, and the model's "1156" replaced
  "56" alone: "11 1156", one of its 21 wrong judged edits. On the
  excerpt `kadesh_redo` the rule makes one edit, "require ments" to
  "requirements". On the whole books, rerun from their kept answers (25
  November 2026), it makes 28 edits: Haynes' book 18, Turney's 3,
  Haskins' 7 (five years such as "11 79" and "A versa" for the town
  Aversa twice); read against galley's text, not the page images, all
  but two or three are one printed word (a compound may be printed with
  a space). Without it, the rule of a neighbour's word repeated, below,
  refuses most of these, and galley's split word stays. A stray letter
  beside a word the model read otherwise, "a hous" against "house", is
  not merged, since the "a" may be a printed word the model left out.
  Two digits are merged only when they join to the model's form: on
  Domesday's table of page 428 galley's "0 8 0" against the model's
  "0 18" would have taken "18", a number of another row, for "8 0"
  (review of 26 November 2026). When they do not, the model's two
  digits replace neither of them: "8" alone would become "18". The token just before is tried first,
  then the one just after. A token
  is merged once: when two merges would take the same token ("Ram ses
  tes" against the model's "Ramses" and "sestes"), the first in galley's
  reading is made and the second gives no edit, since the two, both made,
  would join into one edit that deletes a word.

  Two guards keep a merge from gluing two printed words. A word here is
  one of galley's word list of the book's language (`galley.wordlist`,
  the list structure joins hyphens with), a word of one character only
  when it is a letter in the list in its own case and not a lower-case
  roman numeral ("I" and "a" are words; "i" and "x", which the English
  list holds as numerals, are not), a longer one in any case. When a
  guard holds, the stage makes no edit there. The first version counted
  "i" as a word, since the list holds it, and refused Domesday's "I i,"
  on page 29, the case the merge was made for.

  - When each of the two is one character, they are not merged if both
    are words: "I a" against the model's "It" would lose the "a".
  - When the model's word is one section 6 joined at a line end, they
    are not merged if both are words and the model's word is neither a
    word nor a token of galley's text of the book. The model reads a
    dash at a line end as a hyphen: on Stubbs' page 167
    (`earlyplantagenet01stub`) the page prints "of the body—" and
    "elected" on the next line, the model "body-" and "elected", and the
    merge gave "bodyelected". A word the line end broke has a half that
    is no word, "recog nized", or is printed whole elsewhere in the book,
    "per ishing" (the list has no "perishing"), and stays merged.

  Measured on the whole books rerun from their kept answers (26 November
  2026): of the merges, the guards refuse Stubbs' "body elected" and
  nothing else on Haynes', Turney's, Haskins' and Stubbs' books; with
  the word list alone, without the book's text, they also refused
  "per ishing". No judged edit changes.
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
- **An index or contents entry.** In a block of kind `index_entry` or
  `contents_entry` a replacement needs three more things: the forms at least 0.6 alike; every digit of
  galley's core kept, in order, among the model's digits (made-up
  examples: "12on." to "120n." keeps "1", "2"; "125," to "115," does
  not); and no more digits in the model's core than galley's has digits
  and letters "o", "O", "l", "I" and "i", the letters a digit is read as
  (the letters shaped like 0 and 1, guessed, not measured; "12on." to
  "120n." has three, as many as galley's "1", "2" and "o";
  "116," to "11-16," four against three). An index is printed in two columns of short entries, mostly
  names and page numbers; when the model reads its lines in another
  order than galley, a name pairs with a name of another entry and a
  number with another number, both short enough to pass the 0.3 limit,
  and each block is too small for the rule of words out of place.
  Measured on the 60 judged edits of Haynes' book (an owner's book, so
  described in words; 25 November 2026): 16 are on the index pages, 13
  wrong, each a name or a page number of another line put in the entry,
  and 3 right, each a misread letter in a page number's "n." or an "o"
  read for a zero. The wrong ones are 0.33 to 0.55 alike or change a
  digit; the right ones are 0.6 to 0.86 alike and keep galley's digits.
  The rule takes the 13 wrong and keeps the 3 right. No judged Kadesh
  edit is in an index. The third condition came from Haskins' index
  (`normansineuropea00hask`, 60 judged edits): of its 6 judged index
  edits 5 are wrong, and three of them add digits to a page number that
  galley read right, "73," to "72-83,", "116," to "11-16,", "10." to
  "160.", forms alike enough and galley's digits kept. On Turney's book
  the first two conditions take 13 wrong index edits and 1 right one, a
  page range whose first number galley read as two letters (made-up
  example: "ia-17," to "111-17,"). A contents entry is the same kind of
  short line in columns: on Gierke's contents (`politicaltheorie00gieruoft`,
  80 judged edits, 26 November 2026) structure found the page numbers of
  few entries, so most stay in the entry's text, where the stage may
  change them, and 4 of the 5 judged contents edits are wrong, page
  numbers and short words of another entry ("76" to "68", "of" to
  "Pope"); the three conditions take those 4 and keep the right one.
  A known miss: one more wrong edit on that page, "205" to "227", is in
  a line of the contents that structure made a margin note, so this
  rule does not reach it; the fix is structure's.
- **Three rules for one token.** The three rules that follow, a piece
  of galley's word, a word of another line and a neighbour's word
  repeated, apply only where one of galley's tokens is replaced by one
  of the model's: never to the two halves of a word split at a line end,
  to two of galley's words for one printed word, or to a word galley
  glued that the model reads as two.
- **A piece of galley's word.** A replacement is refused when the
  model's form, its letters and digits alone, is two characters or more
  shorter than galley's and is its start or its end. The model then
  read a piece of the word galley holds whole: the first half of a word
  broken at a line end, which section 6 did not join because the
  model's next line starts otherwise than with a lower-case letter, or
  the second half alone at a column break, or the word without its last
  letters. On Kadesh's page 8 "orientalists" became "orientalis". On
  the seven judged sheets (25 and 26 November 2026), the edits whose
  model form is such a piece are 33 wrong and 1 unclear, and none
  right: Kadesh 1 wrong; Haskins' book 10 wrong, line-end halves such
  as "Norman" to "Nor-"; Stubbs' book 16 wrong, first halves such as
  "Cistercian" to "Cister-" and second halves such as "disinherited"
  to "herited"; Haynes' book 2 wrong, two long words cut back to their
  first syllables and a hyphen; Turney's book 4 wrong, three first
  halves with a hyphen and one second half, and 1 unclear, junk after a
  word taken off with the word's punctuation; Gierke's and Domesday's
  none. One character
  shorter is not refused: on the excerpt `kadesh_redo`, with its
  recorded answers, those are mostly a stray letter galley read before
  a word, rightly taken off ("tof" to "of", "tp." to "p.", "def" to
  "de"), while two characters or more refuse 3 edits there, all wrong:
  "orientalists" twice and "asthe" to "as", which lost "the". The cost
  is 2 wrong judged edits of Haynes' book that the rule would take at
  one character, a possessive's "s" dropped and a misread opening quote
  read as a letter of the word.
- **A word of another line.** A replacement of one token is refused
  when the model's form is six characters or more, less than 0.5 alike
  galley's, and galley's reading of the page holds the same form among
  the 25 tokens before or the 25 after galley's token. The six
  characters were measured (below); the 0.5 and the 25 tokens are
  guessed, not measured. The alignment
  then paired galley's word with a word printed on a line nearby, which
  the model read in another order, often because a margin note sits
  among the lines of a paragraph: on Stubbs' page 87
  (`earlyplantagenet01stub`) "accession," became "Chancellor,", a word
  of the line below, and on page 152 "not" became "almost". Measured on
  the five judged sheets (Kadesh, Haskins, Stubbs and the owner's books
  of Haynes and Turney, 25 November 2026): with these three conditions
  the rule refuses 5 of Stubbs' 38 wrong edits and no right edit. With a
  shorter word it would also refuse right ones, where a short word
  galley misread is printed again nearby ("foe" to "the" on Stubbs'
  page; "alene" to "above" and "Ill," to "III," on Kadesh's), so the
  shorter wrong ones of this kind ("at" to "way", "sidered." to
  "great.") stay.
- **A neighbour's word repeated.** A replacement that covers one of
  galley's tokens is refused when the model's form, its letters and
  digits alone, is that token's form with a part of two characters or
  more, or of digits, before it that is at least 0.5 alike the form of the token just
  before it in galley's reading of the page, or with such a part after
  it alike the form of the token just after it; a fixed token counts, a
  note reference among them. The model then read two printed words, or
  two halves of a word, as one, and the replacement would print the
  neighbour twice. The 0.5 lets a neighbour the model also misread
  count, and is guessed, not measured; the two characters keep "II]," to "III]," beside a roman "I"
  (the excerpt `kadesh_redo`, page 5), while one digit is the end of a
  page range or a note's number glued again. On Kadesh's page 27 the page
  prints "wavy-" at a line end and "lined" on the next line; galley kept
  both halves, the model's "wavylined" replaced "lined", and the page
  read "wavy- wavylined". On the excerpt `kadesh_redo`, with its
  recorded answers, the rule takes 3 of 475 edits, all of this kind:
  "require ments", "can. not" and "con. jectural", where galley split a
  word at a line end and read its hyphen as a space or a full stop, and
  the model's whole word replaced the second half alone. On the 60
  judged edits of Haynes' book (25 November 2026), 7 of the 28 wrong
  edits are of this kind: four where the model read an em dash as a
  hyphen, making the words on both sides one token that replaced one of
  them, so that the word before or after the dash is printed twice; a
  number printed again before itself after a colon; a word broken at a
  line end whose first half was printed again before the whole word;
  and a note reference, a span of its own in galley's block, whose
  number the model glued to the word before it. On Turney's book (an
  owner's book; 60 judged edits, 36 wrong), 11 of the wrong edits are of
  this kind, 7 of them page ranges in the bibliography printed with an
  en dash that galley read as an em dash, so that the range's two
  numbers are two tokens, and the model's one token for the range
  replaced one of them. The two halves of a word
  split at a line end (above) and two of galley's words for one printed
  word (above) are replaced together, and are not refused.
- **An insertion**: a run of the model's tokens that pair with none of
  galley's, inside a note: the galley token before the run is a token of
  the note (its marker or a word of its blocks), and the one after is a
  token of the same note, or the marker or first token of the next note.
  The run's tokens that are only digits are left out of it: they are the
  notes' own numbers, which the model prints and galley holds as markers
  (83 of Kadesh's 183 note markers give no token, empty or "*" or "%"),
  and the page number the model prints between two note columns. So are
  its tokens that hold no letter, digits with signs such as "1/2": on
  Kadesh's page 33 the model put "1/2" after galley's "4:G", where the
  page prints "4:45 (P. M.)", and no insertion of the four judged sheets
  that holds no letter is right (1 judged, wrong). The run's other
  words, joined by one space, go into the note: after
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
  in its note twice; page 51 words of the body put into note 132). Nor
  is a run whose forms, joined, are inside the form of galley's word it
  would go beside: the model read again letters that word holds (in
  Haynes' book a word printed with its letters spaced out, which galley
  holds whole and the model read as the word and then three of its
  letters again; 1 of the 28 wrong judged edits). This holds only for a
  run of two one-letter words or more: one letter is often a word the
  model read right, "à" after "appartenant" on the excerpt
  `kadesh_redo`'s page 1, and words of two letters or more were found
  inside a word galley glued ("is in the" beside "thenumeralisinthe").
  Nor is a run whose first word is galley's token just after it, or
  whose last word is galley's token just before it: the model read a
  word twice, or the alignment met galley's word in another line
  (review of 26 November 2026: Domesday's page 37, "-by Illustrations"
  put in before galley's "-by,", the "by" of a margin note whose
  galley reading is "Tllustrations"). On the seven judged sheets it
  takes 2 wrong insertions, both Domesday's, and none of the 7 right
  ones. Nor is a run each of
  whose words is a word of a margin note printed on the page: the model
  read the margin note into the line beside it. On Gierke's book 5 of
  the 8 wrong judged insertions are so ("rules" with "Majorities", a
  margin note's first word, after it), and none of the 7 right judged
  insertions on the seven sheets has a word of a margin note. A run
  elsewhere, in the body, before the page's first token or after its
  last, is not put in: there it is page numbers and running heads.
- A pair with a fixed token, a pair less alike than 0.3, a pair that may
  hold more words on galley's side, a pair in a block whose words are out
  of place, a pair in an index or contents entry that fails its conditions, a
  pair whose model word is a piece of galley's, repeats a neighbour of
  it or is a word of another line, and a galley token paired with
  nothing, give nothing:
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
| `reason` | `"vision_word"` for a replacement, `"vision_missing_words"` for an insertion, `"vision_note_link"` for a note link (section 9b) |
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

## 9b. Note links

structure links a note to its reference in the text only when the OCR
read the reference as a number or sign it can match (structure spec,
section 11); on Kadesh 142 of its 183 notes have no link, and some links
go to the note before or after the right one. The stage asks the model
where the references are, and links the notes it can place.

**The request.** When `correct_links` is true, on each text page where a footnote starts (a note of
kind footnote whose first origin is on the page), a second request, as in section 4 but for
the prompt:

> This is a page of a book with footnotes. Copy the main text above the
> footnotes, line by line, exactly as printed. Write each footnote
> reference, a small raised number or sign printed after a word, in
> square brackets where it stands. Then write one line for each footnote
> at the foot of the page, in reading order: NOTE, its number, a
> vertical bar, and its first three words. Write nothing else.

An answer cut short gives no links on its page, and is logged as in
section 4. The prompt has no example line: a prompt with one, measured
first, had the model copy the example onto a page that does not print it.

**What the answer gives.** Line by line:

- a **reference** is `[x]`, `<sup>x</sup>`, or a run of superscript
  digits, with x 1 to 3 digits or 1 or 2 of "*", "†", "‡", superscript
  digits read as digits; the model brackets other things too, "[at]" on
  page 27, which are none. With it go the words before it in its line, the last three,
  and the word after it, the marks of other references taken out. A
  reference with no word before it in its line gives nothing;
- a line that gives no reference (a mark with no word before it, as the
  raised number that starts a note copied whole, gives none) and is
  "NOTE" or nothing, then 1 to 3
  digits or "*", "†", "‡", then any of space, comma, full stop, colon or
  "|", then text, is a **note line**: the note's number and its first
  words. The model writes the note lines in other forms than asked
  ("NOTE, 4, Campagne…", or the notes copied whole, "100 Abu Simbel:…"),
  and this takes them all. Only the first note line of each number is
  kept, and only the numbers some reference of the page has.

**Where the reference is.** Among galley's body tokens of the page (its
reading, section 5, less the notes and the removals), the candidates are
the tokens at least 0.75 alike the last word before the reference
(likeness by `difflib`, as section 7). Each is scored: the likeness of
the words before the reference, from the last back, with galley's tokens
from the candidate back, summed, plus the likeness of the word after the
reference with galley's first changeable token after the candidate. The
best candidate is the place when it scores at least 0.5 more than the
second, and when its form and the model's word's differ in length by
one character at most; else the reference gives no link. A misread word
keeps its length within one; on page 45 the model's "order" (the page
prints "ordered") was placed on galley's "ordered'”", 0.83 alike (review
of 19 November 2026). A fixed token is never the place.

An endnote gets no request and no link: Gierke's endnotes start on 93
pages of its endnote section, where no reference is printed, and its
references are matched by structure (structure spec, section 12).

**Which note.** Among the footnotes that start on the page, the one whose
first three words, their comparison forms joined, are most alike the
note line's first three words: at least 0.6 alike, and 0.1 more than any
other note. Else no link, unless the order of the page's notes finds
the note (below). A reference whose number has no note line gives no
link, with the same exception.

**The numbers of a page.** The model reads the raised numbers wrong
often enough that its references and its note lines can agree with each
other and still be one note off: on the whole-Kadesh run of 19 November
2026 a reviewer found, among 27 links outside the twelve reference
pages, all five of page 31's one note too far, and page 21's two, whose
model numbers were 10 and then 7 for the printed 50 and 51. A number
the model marks twice on a page names no note: neither reference gives a
link, by its note line or by the order below, since which of the two the
note line belongs to is not known; nor does any reference after its
first mark, since the count of the model's references is not known from
there on. A misread number often repeats the next one: on page 9, the
model's 8 read as 9 would put "thoroughness." before note 9, and the 9
it marks after "poem" shows the repeat; on page 31 a 17 marked twice
would put the model's note lines, one note off there, back in line with
its references, and four links would go one note too far (reviews of 24
November 2026). A reference whose number the next number the model
marks skips past gives no link either: in 158, 159, 160, 162 the model
may have left out 160 and read 161 as 160, as on page 61, where it
leaves out 160, a 161 read as 160 would put "Hecatæus’s" before note
160. Then a link is kept only when it keeps the order
of the page's footnotes, checked in three steps, each on the links the
step before kept:

- no other link of the page goes to its note: two references whose note
  lines name one note both lose that link. On page 14 the model gives
  references 24 and 25 the same note line, "LD., II, 149d", as the page
  prints the two notes' first words;
- its reference is the k-th the model marked on the page, counted from
  0, and its note the k-th footnote that starts on it. A number the
  model's references skip is not counted as a reference: a reference
  left out and a number misread one too high look alike, and counting
  the skip made wrong links on pages 9, 14 and 31 when one of their
  numbers was changed so (review of 24 November 2026). So on page 61,
  where the model leaves out 160, its 161 to 165 go one note past the
  k-th and are dropped. In this count the footnotes before the link's note
  that galley references and no link of the page goes to count as
  marked: the model does not bracket the heading's "*" on page 8, whose
  note galley links. Page 31's first link went to the page's second
  footnote with nothing before it, and page 21's first to the third.
  A reference the model marks after a galley word that galley's own
  reference follows directly, in the same span's word, counts once, as
  that note marked, whatever note it names: the model marks the
  reference galley read there, perhaps with its number misread. On page
  61 galley links "Luxor" to note 159, whose reference the page prints
  after "says:"; had the model read 159 as 160, note 159 counted as one
  the model left out would have put "says:" before note 160 (review of
  24 November 2026). Until that day a reference naming another note did
  not count galley's as marked, so that on page 9, had galley linked
  "Lenormant," to note 4 and the model marked only "Lenormant," [5],
  the link to note 5 was kept; it is now dropped, one note past the
  k-th. On page 9 galley links "Chabas" to note 6, and the model's "Chabas"
  [6], whose note line matches none of galley's notes, gives no link;
  counted both as the model's third reference and as a note galley
  references, it put the model's "Record" [7], its fourth, one note too
  far, and the page lost that right link (21 November 2026).
  A reference that has no place among galley's words, and whose note
  line names a footnote galley references, counts once too, as that note
  marked: on page 40 galley reads "beaten" as "»aten", so the model's
  "beaten" [103] has no place, and counted both as the model's fifth
  reference and as a note galley references, it put the model's "is."
  [104], its sixth, one note too far, and the page lost three right
  links (21 November 2026).
  Such a count is not known when a reference before the link gives no
  note (no place, no note line, a note line that names no footnote, or a
  number marked twice) and a footnote before the link's counts as marked
  by galley's reference: that reference may be the one to galley's note.
  The link is then dropped. On page 31 galley links "river," to note 78,
  where the page prints 79; had the model's 18 been read 19, its 18 and
  19 would give no note, note 78 would count as marked, and 20 and 21
  would each go one note too far;
- no other link comes before it in the model's answer with its note at
  or after the link's note, nor after it with its note at or before the
  link's; and, when both links' numbers are digits, none comes before
  it with a number at or above the link's, nor after it with one at or
  below. A link is dropped with every link it is out of
  order with, since which of the two is wrong is not known.

The links dropped are logged with their page, and the others of the
page are kept. Until 24 November 2026 a page lost all its links when one
broke the order, which on Kadesh refused whole pages where galley split
one printed note in two or joined two (structure spec, section 11): on
page 62 galley joins note 169 to 168, so the model's 170 and 171 go to
the page's fourth and fifth footnotes as its fifth and sixth references,
and with them fell 166 to 168, which keep the order. On page 31 every
link breaks it (the model's note lines are one note off from the first),
and the page still has none.

The model's numbers are not compared with galley's markers. Until 21
November 2026 they were: each footnote took its link's number, or else
galley's marker, and these numbers had to rise. On pages 26 and 53 the
model misreads the tens of every number, 66 to 68 for the printed 56 to
58, 120 to 129 for 130 to 139, and galley's markers 59 and 137 then
refused all ten links of the two pages, though each goes to the right
note after the right word (`kadesh_reference`). The comparison caught
none of the seven wrong links of the run of 20 November 2026 below
(page 31's markers are no digits, page 21's numbers fall); the k-th
reference rule did. What the model's number gives is the reference's
text in the edit, which the owner sees; the EPUB numbers its notes
itself.

**A note found by order.** A reference placed among galley's words
(above) whose number has no note line, whose note line names no
footnote, or whose note line names a footnote another reference's names
too, is linked by the order of the page's notes when its neighbours fix
the note:

- its number x is digits, marked once on the page, and galley has no
  reference right after its word (that counts as marked, above);
- the next link kept on the page in the model's answer (after the three
  steps above) has a number b above x, and goes to the j-th footnote of
  the page, counted from 0; the note found is the footnote b − x places
  before it, the (j − (b − x))-th, which must exist;
- when a kept link comes before the reference in the answer, with
  number a and the i-th footnote, a is below x, and b − a = j − i: as
  many notes between the two links as numbers. The note found then lies
  between theirs;
- the note found is the k-th footnote for the reference as the second
  step above counts it, the count known, galley references none of it, and no link of
  the page goes to it; a link two references share, which the first
  step drops, does not count here;
- no other reference of the page finds the same note.

A reference is never placed by a page's start or end alone, only before
a kept link: on page 62 the model's 169 has no note (galley joined it to
168), its link after, 170, is dropped by the order, and by 168, its
link before, it would go to the next footnote, which is 170's. The model's numbers place the note, so a misread tens
digit (pages 26 and 53) does not move it, as long as the two neighbours
are misread alike.

On page 11 the note lines "MASPERO's" and "Geogr." of references 16 and
17 match no footnote, since galley reads the notes' first words as
"Masrvuo's" and "i @engr."; between the links 15, to the first footnote,
and 18, to the fourth, they go to the second and the third. On page 29
the model's numbers are 2, 3 and 4 for the printed 72 to 74, the note
lines of 2 and 3 ("Op. cit., p. 164.", "Op. cit., p. 543.") are too
alike galley's three "Op. cit." notes to choose, and 4 goes to the third
footnote: 2 and 3 go to the first and the second.

**Measured** on the 22 pages of the three Kadesh excerpts where a
footnote starts (pages 8 to 15, 29 to 33, 36 to 38, 59 to 63 and 66), on
the answers of the 35B model recorded on 24 November 2026
(`tests/fixtures/correct/kadesh_links/`), against galley's whole-book
structure: the links went from 24 to 42, 35 of them kept by the three
steps and 7 found by order. All 42 are right, checked against
`tests/fixtures/expected/kadesh_reference/note_references.json`, the
references read from the page images, which now covers the 14 pages
with links. The links lost are on pages 13, 31, 36
and 38 (galley's split, the note lines one note off, galley's note left
in the body, note lines of one word), those after a split or a join on
pages 11, 14, 62, 63 and 66, and 159 and 161 to 165 on page 61, around
the reference the model leaves out (159 gives no edit: galley links its
note elsewhere). Counting the skipped number as a
reference gave those 5 too, all right, but made wrong links when a
number was misread.

**The link.** The galley word that holds the place's token, its
whitespace word, gets a reference to that note right after it:

- when a reference span follows that word directly and refers to the
  same note, nothing is proposed: galley has the link;
- when it refers to another note, the link takes its place;
- else the link is put in after the word. galley's word may still hold
  the reference as the OCR misread it, after its punctuation: "forces.3",
  "enemy;™", "Zahi“". The characters after the core of galley's word
  (section 6), the core less what is no letter or digit at its end,
  past as many as the model's word has after its core so cut
  (quotes made straight on both sides, and equal there), are the
  misread reference when they are 1 to 3, each a digit or one of
  `' " ‘ ’ “ ” * † ‡ ™ ® ^ %`. They leave the word, and are kept only in
  the edit's `old`. Otherwise the word stays whole. The core is cut
  because section 6 keeps in it a sign that is no ordinary punctuation,
  and so the punctuation before the sign: "soldiers;™" is one core, and
  until 21 November 2026 the link went after its "™" ("soldiers;™",
  "map®", "iter™", "whatever.™" on Kadesh). But a sign the core keeps
  may be printed ("50%", "40°"), so of the misread reference, the
  characters that are in galley's core, past those of the model's word,
  must each be "™", "®" or "^", signs the OCR gives for a raised number,
  which the model's word then lacks; when one of them is another
  character, or when they are not all taken as the misread reference,
  the reference gives no link. "map®", where the model has `map [43]`,
  becomes "map" with the link; "50%", where the model has `50 [3]`, gets
  no link; "map®", where the model has `map® [43]`, keeps its "®" and
  the link follows it. Measured on the seven books (the runs of the
  note-links plan, 21 November 2026): each of the cores of galley's
  words that end in "™", "®" or "^" (Kadesh 19, Domesday 40, Gierke 61,
  Stubbs 11, Haskins 11, Turney 8, Haynes 1) is a misread raised number
  or OCR noise ("description™", "map®", "undoing.^", "(37)®"), none a
  printed sign; "%" and "°" also end numbers ("111.1%", "40°" on
  Kadesh). The reference's
  text is the model's number x, so that the edit shows which number the
  model read. "advanced.”", where the model has
  `advanced." [4]`, keeps its quote. A quote is taken as part of the
  misread reference only when the reference's number is not in galley's
  word: in "soldiers.”37" against the model's "soldiers." the reference
  is "37" and the quote, which the model left out, stays (review of 19
  November 2026, finding 3). What is taken out is not shown: it is
  dropped from `book.md` and the EPUB, where a footnote's reference is
  Pandoc's `[^n-p0008-004]`, and kept only in the edit's `old`, where
  the owner sees it.

A link is not proposed, and is logged, when:

- the stage's word edits (section 7) change that word: each edit must
  apply whether or not the others do;
- a reference span follows the word after white space (";13" in
  "14) ;13" on page 10): the link would stand beside galley's;
- after all the links of the book, its note would have a reference from
  galley that no link of the stage takes the place of: a footnote is
  referenced once (markdown refuses two). Refusing a link brings back
  the reference of galley's it would have taken the place of, so this is
  checked again until no link is refused: had galley linked
  "Lenormant," to note 4 and "Chabas" to note 5 on page 9, as it did
  until 21 November 2026, the model's "Lenormant," to note 5 would be
  refused while galley links note 5 from "Chabas", and then "Salvolini"
  to note 4 too, since galley's "Lenormant," to note 4 stays;
- two links of the book go to the same note: neither is proposed;
- two links of the book follow the same galley word: neither is
  proposed. Markdown would put the second edit's link in place of the
  first's, and which of the two references is right is not known
  (review of 24 November 2026).

**The edit.** `reason` `"vision_note_link"`; `old` galley's word, with
the words before it in the same span added one at a time until it
occurs once, as section 8 says, but only before, so that the reference
stays at the end of `old`; `new` is `old` less the misread reference,
followed by the link written as markdown writes a link to a note,
`[x](#n-p0008-004)`, with the model's number x in the brackets (a `[`
or `]` in it is left out). `second_reading` is null. The link edits come in
`edits/correct.jsonl` after all the word edits, in page order and, on a
page, in the order of the text, so that a word edit applies before the
link edit beside it splits the span.

**Measured** with the 35B model on the twelve pages of the reference
`tests/fixtures/expected/kadesh_reference/note_references.json` (pages
8, 9, 11, 13, 15, 25, 26, 27, 29, 40, 47 and 53, read from the page
images), 19 November 2026, against galley's links in the run of that
day: of the 62 references printed there, 57 have a note of galley's of
their own to go to (galley joined the other 5 notes to the note before);
galley linked 8 of them rightly, 6 to the wrong note, and left 43
unlinked. With this prompt and these rules, before the checks against
two links to one note, the model's answers give 32 links, none wrong: 23
where galley had none, 3 that put a wrong link of galley's right, and 6
that galley has already (which propose nothing).
The model took 21 to 88 s a page, 49 s on average, with another model
of the owner's running on the same machine. A prompt that asked only
for each reference's line, with an example line, gave 36 links with 1
wrong (on page 13 it numbered a note line 22 for the note printed 23).
On pages 11 and 27 the model marks the references, but no note line of
its answer matches one of galley's notes, so they get no links. These
twelve pages were measured before the rules of the numbers of a page,
the word's length and the reference's text were added.

**Measured on the whole book**, Kadesh, 20 November 2026, every link
checked on the 300 dpi page images (the 35B model; the stage's answers
differ between runs at temperature 0, so each run is its own sample):

| run | links | right | wrong |
|---|---|---|---|
| before the review's rules | 79 | (8 wrong among 27 a reviewer checked outside the twelve pages) | |
| with the word's length and the order of numbers | 68 | 61 | 7 (page 21: 2, page 31: 5, each one note too far) |
| with the k-th reference to the k-th footnote too | 40 | 40 | 0 |

In the last run 14 pages lost their links to the rule of the numbers of
a page, and the notes linked in the book went from 41 to 76 of 183. The
stage took 3,705 s for 44 pages against about 474 s without links,
with another model of the owner's running on the same Mac.

**The pages without links**, measured 21 November 2026 on new answers
of the 35B model for the 42 pages where a footnote starts (the answers
of the run above were not kept, and differ at temperature 0). On the 13
pages that run left without links, the causes, from the answers and the
page images:

| cause | pages |
|---|---|
| galley split one printed note into several, or made a note of other text, so the k-th reference is not the k-th footnote | 13 (the list of sources, note 22, split in eight), 46 (a line of junk before the first note, note 111 split in two), 63 (note 173 split in two) |
| galley joined two printed notes, or left one in the body | 29 (72 joined to 71 of page 28), 62 (169 joined to 168), 36 (87 left as a paragraph of the body) |
| the model's note lines are one number off its references | 31 (it left out note 76's line and numbered the others from 17) |
| the model left a reference out | 61 (160) |
| notes whose first words are alike, "LD., II, 149d" or "Op. cit., p.", so a note line matches no note or the wrong one | 14, 28 (where no new link was possible) |
| galley's word misread, the model's reference has no place | 40 |
| the model misread the tens of every number | 26, 53 |

The rule for a reference with no place, and the end of the comparison
with galley's markers, link pages 40, 26 and 53: 13 more links, all to
the right note after the right word, against `kadesh_reference`, which
covers the three pages. On the 42 pages the stage's link edits went
from 43 to 56, and no other page changed; the links that equal galley's
own, page 28's two among them, give no edit and are not counted. A rule that left out of the count a
reference whose number has no note line was tried and lost 5 right
links (pages 9 and 20) and gained none.

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

**A link edit** is an edit whose `new` ends with a link to a note,
`[x](#<note id>)`, x holding no bracket, and whose `old` holds no such
link. Whoever writes it, it applies when rules 1 to 4 hold and:

5. the note id is the id of a note of blocks.json.

Then `old` is replaced by `new` less the link, and a reference span
follows it in the block: its text x, its emphasis that of the span, its
`note_ref` the note id. When a reference span already follows the
replaced text directly, the new one takes its place. Afterwards each note
whose references a link edit changed, the one it links and the one whose
reference it replaced, is `referenced` when a block refers to it, and
not otherwise.

6. Once every edit is made, a footnote a link edit links to is referred
   to by one reference only. A link edit that breaks it, an owner's link
   to a footnote galley already links, or a link of correct's whose
   replaced reference came back when another line was deleted, is listed
   with its file and line like an edit that breaks another rule. It is
   checked once all the edits are made, since correct's links may each
   take a reference that another of its links gives back (section 9b,
   page 9).

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
- To undo a note link: delete its line, as any edit's. A link that took
  the place of a wrong link of galley's brings that one back; when
  another link of the stage gave its note a reference, the footnote is
  then referenced twice, and markdown stops and names it: delete that
  line too. A link cannot yet be rejected for good: an edit of the
  owner's cannot remove a reference (rule 4), and correct proposes the
  link again on its next run.

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
find by reading, which is why the stage is off by default (section 16).

## 12. The public interface

The stage's entry point, as every stage's (architecture section 9):

```python
def run(folder: BookFolder, config: BookConfig, *, workers: int = DEFAULT_WORKERS) -> None:
    """Write edits/correct.jsonl: the vision model's fixes to galley's words
    of every text page, as edits, its answers kept in answers/ and read
    from there when the request is the same (section 4b). Raises
    ExternalProgramError when LM Studio does not answer or lacks the model,
    InputFileError for stale inputs or a kept answer it cannot read."""
```

The check `cli.py` makes before any stage when a command runs correct
and the book folder has no `answers/`, and the stage before its first
request:

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
PNG with Pillow, reads the kept answer or, after the one check of the
server (section 4), sends the request and waits (section 4b), then makes the page's edits
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
- **A word split at a line end that structure did not join.** In the
  note of page 8, galley's "cam- P#@igns" against the model's
  "cam-" and "paigns" gives one edit, "cam- P#@igns" to "campaigns"; on
  page 61, "Dirporr- MCiuer," against "DINDORF-" and "MÜLLER," gives
  "Dindorf-Müller,".
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
- **The kept answers** (section 4b), their tests named with
  `answer_store`: the excerpt `kadesh_redo` run twice in one book folder
  with the test's server, the second run sending no request and writing
  the same `edits/correct.jsonl`; run a third time with another model,
  every request sent again; and, on one request with a literal image,
  another prompt or model asking again, the same request asking nothing,
  an answer cut short kept and used, a failed request keeping nothing, a
  file cut in the middle, not JSON or of another `format_version` an
  `InputFileError` naming it, and `answers/` left by
  `delete_stage_outputs`.
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
- **Note links** (section 9b). The main test is the excerpt
  `kadesh_redo` with the 35B model's recorded answers to the prompt of
  section 9b for its pages 0, 1, 3 and 7 (Kadesh's 8, 9, 11 and 15): the
  link edits are written as literals, checked against the reference
  pages, and markdown applies them. The recorded answers do not reach
  every rule (no endnote, no owner's link, no quote before a number), so
  the rules are tested one by one too, on literal answers, tokens, notes
  and blocks, through the module's functions that each rule lives in:
  the answer's references and note lines in each form the recorded
  answers show, the place and the note, the misread reference, each
  refusal, the order of the reference numbers, and markdown's rules 5
  and 6, each with its error.
- **Kadesh, the links**, by hand: the whole book; the notes linked before
  and after; each link of the twelve reference pages checked against the
  reference.
- **Kadesh**, by hand, at the end of work package 4: the whole book with
  `correct = true`; on the six pages of the measurement, galley's reading
  of each page (section 5) with the edits applied, scored against the
  measurement's reference (`tmp/measure/ref/`) by its own scoring, body
  and notes apart, its fluent wrong words counted, against its 0.7 and
  3.4 and against galley's reading without the edits; the share of wrong
  note edits the second reading would flag, from the recorded 27B
  answers; and the time for the book.

**What the fidelity check cannot see.** markdown's fidelity check
(architecture section 13) compares the words of blocks.json with those
of book.md less the removals and counts every edit's change as allowed,
so a word an edit loses or puts in twice passes it: the review of 26
November 2026 found such edits on the whole-book reruns ("towitesand"
to "wites and", "909" to "0 9", "-by Illustrations -by,") with the
check passing. A check that could see them, proposed and not built:
for each edit, compare the tokens of `old` and `new` by least edits
(section 7) and count the tokens of `old` that pair with none of
`new`'s and the tokens of `new` that pair with none of `old`'s, less
the ones the edit's kind allows (one token of `new` for each split of
a glued word, the run of an insertion, none lost for a replacement or
a merge, whose letters and digits must hold all of `old`'s but for the
ones read otherwise); the stage would log every edit with a token
lost or put in beyond that and the evaluation tool would list them
beside the sheet, so that a rule that loses words shows on the whole
book and not only on the judged sample.

## 16. Decided

1. **How the stage is used, given about 1 fluent wrong word in 300**:
   decided by the owner on 19 November 2026, option (b) of the three
   put to them (the stage as specified; with the second reading; not
   used). Kadesh runs with `correct = true` and the second reading
   (`correct_second_model`), and the doubtful edits are checked against
   the page images by the assistant, which writes the ones it rejects to
   `edits/owner.jsonl` (section 11); a book whose OCR is good keeps the
   stage off until the stage is measured on a second book. The stage
   stays off by default.

2. **Whether the stage is on for a book whose OCR is good**: measured on
   Domesday (`domesdaybook00maituoft`) on 21 November 2026, and the
   recommendation is **off**; the owner decides. Domesday's text layer
   is good in English and poor in Latin and Old English, which its notes
   and appendices quote at length. Its tables are not read as tables:
   structure made the rows of the table on page 426 into footnotes, their
   cells out of the printed order.

   *What was measured.* Six pages read word by word from the page images,
   2,485 words as section 6 cuts them, in `tests/fixtures/expected/domesday_reference/pages.json`:
   pages 100 and 180 (body and Latin footnotes), 250 (body), 316 (an
   appendix of Latin and Old English charter extracts), 426 (a table of
   counties) and 470 (body, a small table, four footnotes). The stage ran
   on these pages alone, as `run` does for each page, with the 35B model,
   note links and the second reading by Qwen 3.6 27B, on the owner's Mac
   while another program of the owner's used the 27B model. galley's
   reading of each page (section 5) was scored against the reference
   before and after the edits: its words lined up with the reference's
   by least edits, and the wrong, missing and extra words counted per 100
   words of the reference, compared in the comparison form of section 6.
   The side notes, the short headings Domesday prints in the margin, were
   put in the reference where galley reads them, so that their place is
   not counted. The table of page 426 is compared without its order,
   since galley's order of its cells is not the printed one: the count is
   of the words one side has more times than the other. Whether each edit
   is right was decided by hand, against the reference and the images:
   an edit whose new word is right but leaves an extra word beside it is
   wrong.

   | text | words | wrong before | wrong after |
   |---|---|---|---|
   | body, English (pages 100, 180, 250, 470, and the heading of 426) | 1,417 | 6 (0.4 in 100) | 3 (0.2 in 100) |
   | body, Latin and Old English (page 316) | 469 | 32 (6.8 in 100) | 13 (2.8 in 100) |
   | footnotes (pages 100, 180, 470) | 371 | 23 (6.2 in 100) | 10 (2.7 in 100) |
   | small table (page 470) | 27 | 4 | 1 |
   | side notes | 17 | 0 | 0 |
   | table of page 426, order left aside | 184 | 13 | 18 |

   *The edits.* 77 word edits, of which 23 are wrong: 17 on the five
   pages without the table of page 426, 6 on that table.

   - On the five pages without that table, 67 edits, 50 right and 17
     wrong. 12 of the wrong ones turn a word galley read right into a
     wrong one ("resolvat" to "resolut" three times, "munitione" to
     "munitio ne" twice, "affirmative" to "baraffirmative", the side
     note's "bar-" joined to the body's word, "Aluuinus" to "Aluinus"),
     and 2 put in a word that galley has already beside it ("team lands"
     to "team teamlands", "Heraldo... Terra" to "Heraldo...Terra...
     Terra"), and 3 change a word galley read wrong into another wrong
     one. 2 are fluent wrong words, wrong words that read as real ones:
     "oðrum" and "geworce", Old English words printed elsewhere on page
     316, where the page prints "oþrum" and "gewerce".
   - On the table of page 426, 10 edits: 4 right (2 put in a letter the
     table lacked, 2 put back a number another edit took away) and 6 wrong, which put in a word the
     table already has, in the wrong row (the counties "Surrey",
     "Berkshire", "Cornwall", and three numbers), all 6 fluent;
     "Berkshire" takes the place of "Hampshire", which is lost.
   - The second reading marks 11 edits doubtful, 9 of them wrong: the 6
     wrong edits in the footnotes of pages 100 and 180, and the 3 county
     names on the table; the three numbers put in twice it reads as the
     35B model does, and does not mark. The 11 wrong edits in the body
     are not marked, since the second reading reads only the footnote
     band (section 9); 9 of them are on page 316.

   *Links.* 2 links, both right: on page 470 they take the place of two
   wrong links of galley's. A third was galley's already. Page 180's first
   note gets none: its first words, "D. B. i. 238 b", are those of its
   eighth note too, so the note line matches neither (section 9b).

   *Time.* The 35B model took 9 to 14 s a page to read it, 11 s on
   average, and 7 to 10 s more for the note references; the 27B model 16
   to 54 s for a footnote band, 30 s on average. For Domesday's 539 text
   pages, 489 of them with footnotes, that is about 3 hours without the
   second reading and about 7 hours with it; the 27B model's times may be
   too high, since another program was using it.

   *Why off.* Outside the table of page 426 the stage takes the wrong
   words from 65 to 27, but the gain is not in the English text, where
   it would show on every page. In English, where galley's reading has
   0.4 wrong words in 100, the stage made 5 edits on the four pages: 3
   right, 1 wrong ("baraffirmative") and 1 that left a broken word's
   first half ("team teamlands"); that is 3 wrong words fewer in 1,417.
   The gain is in the Latin and Old English: the footnotes from 6.2 to
   2.7 wrong words in 100, and to about 1.3 (5 wrong words in 371) when
   the doubtful edits are checked and the wrong ones undone, as item 1
   has it for Kadesh; page 316 from 6.8 to 2.8, with 9 wrong edits the
   second reading does not mark, since they are not in a footnote; and
   the table is made worse. Getting the footnotes' gain takes about 7
   hours for the book and checking against the images some 1,000
   doubtful edits (6 on the three measured pages with footnotes, 100,
   180 and 470, so about 2 on each of the book's 489 pages with
   footnotes), while the body's Latin
   quotations keep wrong edits nobody is told of. That is why the
   recommendation is off for a book like Domesday: the English, which is
   most of what is read, gains nothing a reader would see. The case for
   turning it on is a book whose quotations in another language matter
   to the owner more than that cost; it then wants the second reading,
   the doubtful edits checked, and the edits in quotations printed in
   the body, as on page 316, checked too. Leaving out the pages whose
   tables structure turned into notes would remove the table's harm; it
   is not built.

3. **Rules measured on the judged edits and not adopted** (25 November
   2026, plan `misread-words`, work package 3). Seven books' samples
   were judged against the page images, 60 edits a book for Kadesh,
   Haskins (`normansineuropea00hask`), Stubbs (`earlyplantagenet01stub`)
   and the owner's books of Haynes and Turney, and 80 for Gierke
   (`politicaltheorie00gieruoft`) and Domesday (`domesdaybook00maituoft`).
   Each item below names the sheets it was counted on; the first four
   were counted on Kadesh, Haskins, Haynes and Turney, before the other
   sheets were judged. These rules took as many right edits as wrong
   ones or more, outside what the rules of section 7 already take, and
   are not in the stage:

   - **A stricter likeness for every replacement**, 0.5 instead of 0.3:
     outside the index pages it refuses 3 right edits (Kadesh 2, as
     "Ill," to "III,", and 1 on Haskins' book), and
     the wrong ones it would take are mostly on index pages, which the
     rule of an index entry takes already.
   - **No change of one digit into another**: outside the index pages
     the four sheets hold 3 such edits, all right (Kadesh "1985," to
     "1885," and "349." to "549.", and one number on Turney's book).
     Gierke's sheet has one wrong such edit outside an index or
     contents entry, "205" to "227" on page 65: a line of the contents
     that structure made a margin note, so the rule of a contents entry
     does not reach it. That miss is structure's, not this stage's.
   - **A letter with a diacritic galley read kept**: 1 wrong edit
     (Kadesh's "Hammamét," to "Hammāmāt,", printed with circumflexes)
     against 1 right (Haskins' "Béhmer," to "Böhmer,").
   - **No accent put on a name the model read in small capitals**: it
     would take Kadesh's "GurEyssE" to "Guéysse", 1 wrong edit, and
     undo "Dirporr- MCiuer," to "Dindorf-Müller," (section 14), right.

   - **No real word replaced by another real word one letter away**,
     for spellings the model modernises (Stubbs' "Despensers" to
     "Despencers", five judged edits, and "ascendency." to
     "ascendancy."): with both words in galley's word list it refuses
     1 wrong edit on the five sheets and 39 right ones (Kadesh 15,
     Haskins 10, Stubbs 7, Turney 6, Haynes 1), since the OCR's own
     errors are often real words ("fer" for "for"); with galley's word
     printed the same way 3 times or more in the book and more often
     than the model's, it refuses 7 wrong (Stubbs' five "Despensers"
     among them) and 12 right, since a misreading the OCR repeats on
     every page, as "rn" read "m", is as frequent as a true spelling.

   - **A Latin word not changed by one vowel or one letter**: galley's
     word of four letters or more in Tesseract's Latin list and not in
     the English one, changed by one vowel or one letter more or less.
     On Gierke's sheet (80 judged edits, Latin 13 right and 5 wrong) it
     refuses 2 wrong; on Domesday's (80 judged, Latin 20 right and 4
     wrong) none; it also refuses 1 right edit on Kadesh's sheet and 1
     on Stubbs'.
   - **No insertion of a run galley's reading of the page holds**, one
     word or more, anywhere on the page: on the seven sheets it refuses
     8 wrong insertions, 5 of them those the margin-note rule takes, and
     3 right ones (Kadesh's "AA", Domesday's "i" and "Gloucester").
     **No insertion of one-letter words**: 4 wrong (Haskins' "f",
     Domesday's "a" and the signature mark "M", and one on Haynes' book
     that the rule of letters held already takes) and 1 right
     (Domesday's "i", a volume of a citation).

   Passages in another language, which the Domesday trial found
   wrongly corrected, wait for the whole-book runs of Domesday and
   Gierke.

## 17. Not in this spec

- `galley2epub edits-from`, by which the owner writes edits from a
  corrected copy of `book.md`: part of the markdown spec, not written.
- Reading only the footnote bands with the main model, which the
  measurement found cheaper when the body is already good: not built.
- Another prompt, resolution or model: one prompt and 300 dpi were
  measured.
- How the stage does on books other than Kadesh and Domesday: not
  measured (section 16, item 2).
