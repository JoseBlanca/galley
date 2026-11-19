# Reading Kadesh's bad print better: the measurement

This report is the measurement the plan `docs/plans/notes-vision.md`
asks for before galley's optional correct stage is designed (the stage
that proposes fixes to OCR errors, run when a book's `book.toml` has
`correct = true`; the plan's work packages 3 and 4 specify and build
it). Written on 19 November 2026. It measures how many words galley gets
wrong on six pages of Kadesh (`battleofkadeshst00breauoft`), whose notes
are blurred on the scan itself, and how many each other way of reading
them would get wrong: the scan's text layer, Tesseract, a combination of
the two, and three vision models (language models that read images) run
locally in LM Studio, the program on the owner's Mac that serves local
models. It decides what the correct stage is built on: Qwen 3.6
35B-A3B reading every page, its words replacing galley's where the two
line up word for word. On the six pages this brings the notes from 26.5
wrong words in 100 to 3.4, and the body from 2.0 to 0.7, at the cost of
about 1 wrong word in 300 that reads as a real word.

## What was measured, and how

**The reference.** I transcribed six pages from the page images, word by
word, reading crops enlarged two to four times: pages 8, 9 and 11 (the
plan's three), 15 (two columns of blurred notes, most of them numbers),
27 (two blocks of hieroglyphs) and 29 (a map with its caption). Page
means the page index of the PDF, from 0. The reference holds 1,975 body
words and 1,356 note words, 1,107 of them on the three pages whose notes
are worst blurred (11, 15, 27). 33 words, nearly all page and line
numbers inside citations, I could not read; they are left out of the
scoring, and any reading of them counts as right. The running heads,
page numbers, hieroglyph rows and map labels are in the reference but
not scored. The files are in `tmp/measure/ref/`, one per page, each line
marked body, note or other.

Where a note is blurred, I read some words partly from their shape and
partly from what the sentence needs ("superimposed", "repetitions" on
page 15). A model that guesses from the sentence in the same way would be
scored right there even if it did not see the word, so the models' rates
in the notes may be a little too good. How much is not measured.

**Word error rate.** Each reading is aligned with the reference word by
word, by the least number of edits, and its rate is the number of wrong
words, missing words and extra words for every 100 words of the
reference. Before the alignment both sides are made comparable: a word
broken by a hyphen at a line end is joined, curly quotes are made
straight, punctuation at the ends of a word, accents, superscripts and
case are dropped, and a note marker glued to a word ("Greece,1") is cut
off. A note's own number may be read or left out without cost. The body
and the notes are counted apart; an extra word counts where it falls.

**The readings.**

- The **text layer**: the words stored in the PDF itself, invisible over
  the page image, which the Internet Archive's OCR put there; read with
  pdfplumber.
- **Tesseract** 5.5.4 on the page rendered at 300 dpi, in three page
  segmentation modes (how Tesseract looks for text on the page): 3, the
  default, finds blocks and columns; 4 reads one column of lines of
  varying size; 6 reads one uniform block. 1.2 s a page.
- **galley's current output**, made with `ocr = "redo"`, the setting
  under which galley reads every page again with Tesseract and puts back
  from the text layer the note markers and the lines Tesseract missed:
  the words galley's extract stage wrote for Kadesh
  (`runs/ocr-redo/battleofkadeshst00breauoft/words.json`), before they
  are joined into paragraphs and notes. "galley" below means this
  reading.
- An **oracle**: a word counts as right if any of the readings named
  reads it right. It is the most any rule choosing between those
  readings, word by word, could gain.
- A **combination** of the layer and Tesseract (mode 3): where they
  differ, the word in galley's English word list (Tesseract's, 338,080
  words) wins; where both or neither are in it, Tesseract's word if its
  confidence is 70 or more, else the layer's. A word only one of them
  has is kept when it is in the list or Tesseract's confidence is 70 or
  more. Thresholds of 0, 50, 90 and 101 did worse.
- Three **vision models** in LM Studio on the owner's Apple M5 Pro
  with 64 GB, at temperature 0 with reasoning off: Qwen 3.6 35B-A3B
  (a mixture of experts that runs 3 billion of its weights for each
  word) and Qwen 3.6 27B, both already installed, and olmOCR 2 7B, a
  model trained for OCR of documents (Allen AI), downloaded for this
  (6 GB). All three are stored with their weights rounded to about 4
  bits, the form LM Studio offers for this machine. Each was given the whole page at 300 dpi, or the note
  band (the strip of the page from the first note line down, at 300
  dpi, cropped by hand at the top of the notes), with the prompt:
  "Transcribe the printed text in this image exactly as it is printed,
  line by line, in reading order. Do not correct spelling or wording, do
  not add anything, no commentary, no formatting. Skip hieroglyphs and
  drawings." olmOCR read whole pages with its own prompt at the size it
  was trained on (1,288 pixels high, 127 dpi).
- galley's words **merged** with the 35B model's reading, two ways.
  Both align the model's words with galley's words of the same page (or
  of the note band); where one of galley's words lines up with one of
  the model's and they differ, the model's word is taken. "Aligned only"
  keeps galley's other words and drops the model's words that line up
  with none of galley's; "aligned and gaps filled" also puts in the
  model's words where galley has none.

**Fluent wrong words** are what the plan calls invented text: a wrong
word that reads as a real word, so that nothing on the page shows it is
wrong. I counted, in each model's output, the wrong and extra words of 3
letters or more that are in galley's word list or printed elsewhere on
the page. The same count is not given for Tesseract and the layer,
because the word list holds many of their junk readings ("tue", "cam",
"ner"), which no reader would take for text.

## The results

Word error rate in wrong words per 100 words of the reference, on the
six pages; the fourth column is the notes of pages 11, 15 and 27 alone.
Time is per page or per note band, averaged over the six.

| reading | body | notes | notes, blurred pages | fluent wrong words | time |
|---|---|---|---|---|---|
| text layer | 4.5 | 45.0 | 45.1 | | |
| Tesseract, mode 3 | 2.0 | 28.2 | 32.3 | | 1.2 s |
| Tesseract, mode 4 | 4.3 | 30.3 | 35.0 | | 1.2 s |
| Tesseract, mode 6 | 3.8 | 32.2 | 36.9 | | 1.2 s |
| galley, `ocr = "redo"` | 2.0 | 26.5 | 30.7 | | |
| oracle: layer, Tesseract mode 3 | 0.6 | 16.4 | 18.6 | | |
| oracle: layer, Tesseract modes 3, 4, 6 | 0.5 | 12.3 | 13.8 | | |
| combination of layer and Tesseract | 1.4 | 24.4 | 26.8 | | |
| Qwen 3.6 35B-A3B, page | 0.9 | 2.8 | 3.2 | 11 | 12.8 s |
| Qwen 3.6 35B-A3B, note band | | 2.3 | 2.3 | 5 | 6.5 s |
| Qwen 3.6 27B, page | 1.6 | 2.6 | 2.6 | 8 | 76.7 s |
| Qwen 3.6 27B, note band | | 2.4 | 2.5 | 3 | 28.2 s |
| olmOCR 2 7B, page, own prompt | 0.6 | 4.9 | 5.4 | 18 | 33.8 s |
| olmOCR 2 7B, note band | | 4.4 | 4.4 | 12 | 12.0 s |
| galley + 35B page, aligned only | 0.7 | 4.9 | 5.4 | | |
| galley + 35B page, aligned and gaps filled | 1.1 | 3.4 | 3.8 | | |
| galley + 35B band, aligned only | 2.0 | 4.7 | 5.1 | | |
| galley + 35B band, aligned and gaps filled | 2.1 | 2.8 | 2.9 | | |

What the table says:

- **Combining the readings galley has does not fix the notes.** Even the
  oracle, which always picks the right reading when one exists, leaves
  12.3 note words in 100 wrong (16.4 with the layer and Tesseract's
  mode 3 alone): on the blurred notes every reading
  is wrong at the same word. The simple combination gains 2 words in
  100 in the notes and 0.6 in the body.
- **Each vision model reads the blurred notes 5 to 11 times better
  than galley**: 2.3 to 4.9 wrong words in 100 against 26.5. On page 11,
  galley's "Masrvuo's statement (Struggle, p. 3%) that it is "a puem ia
  rhymed struphes."" is the 35B model's "MASPÉRO's statement (Struggle,
  p. 395) that it is "a poem in rhymed strophes,"".
- **The two Qwen models are equally good; the 35B model is 4 times
  faster on a note band and 6 times on a page.** olmOCR, though trained for OCR, makes twice their errors in
  the notes and the most fluent wrong words, many of them numbers
  rounded off: "2,000 chariots" for "2,500", "3,000" for "3,500",
  "10,000" for "10,500" (page 15).
- **The vision models leave out what is not text.** On the hieroglyph
  rows of page 27, galley's output has 44 words of junk; the Qwen models
  have none.
- **Merging into galley's words keeps most of the gain.** Taking the
  model's word only where it lines up with one of galley's gives 4.7 to
  4.9 in the notes; filling the gaps as well gives 2.8 to 3.4, close to
  the model's own text.

On the six pages, the 35B model reading whole
pages gave 11 among 3,331 scored words: "Borchardt" for "Brugsch" twice
(both names are on page 11), "orientalis" for "orientalists" twice
(page 8, in the body, where galley was right), "Med." for "Hist.",
"Rev." for "Rec.", "Egyptian" for the printed misprint "Eygptian". The
27B model on page 15's notes wrote "Ramesses" for "Ramses", a correction
the prompt forbade. Other ways the models differ from the page, which
the merge must allow for:

- They drop note markers in the body or turn them into superscripts, and
  print page numbers and running heads as text.
- The 27B model, reading the whole of page 29, left out the map's
  caption, 13 words.
- The note numbers come out at the start of each note, where galley's
  structure expects them.

A second model reading the same note bands catches most of the first
one's wrong words. Of the 35B model's 33 wrong or extra note words, the
27B model reads 24 differently from it; of its 1,330 right note words, the
27B model reads 9 differently from it.

## The recommendation

Build the correct stage on **Qwen 3.6 35B-A3B in LM Studio, reading
each text page whole at 300 dpi**, with the prompt above and reasoning
off, and **merge its words into galley's words** rather than replace
galley's text:

1. Align the model's words with galley's words of the same page, by
   least edits after the normalisation of this report: two words line
   up when the alignment pairs them, whether they are equal or not.
2. Where one of galley's words lines up with one of the model's and they
   differ, the edit replaces galley's word with the model's.
3. In the notes only, where the model has words that line up with none
   of galley's, the edit inserts them. In the body this added more wrong
   words than right ones (page numbers, note numbers), so it is not
   done there.
4. galley's note markers, its order of blocks and its other words stay.
   The model's text is never taken whole, because of what it drops (note
   markers, a caption) and adds (page numbers).
5. Each edit records galley's word, the model's word and the page, so
   that the owner can see and undo it.

What it gives, on the six pages: notes from 26.5 wrong words in 100 to
3.4, body from 2.0 to 0.7 (the notes of the table's row "35B page,
aligned and gaps filled", the body of its row "aligned only"). It makes
443 edits there: in the notes 403,
of which 362 right and 41 wrong, 8 of these fluent; in the body 40, of
which 33 right and 7 wrong, 3 of these fluent. The risk is the 11
fluent wrong words among 3,331 words, about 1 in 300; on Kadesh's 44
text pages, which hold 24,548 words, about 80 in the book, among some
3,000 edits, too many to check by eye. At 12.8 s a page, Kadesh's 44
text pages take about 10 minutes.

Reading only the note bands is the cheaper choice when the body is
already good: 6.5 s a band, about 5 minutes for Kadesh's 43 pages with
notes, notes at 2.8 after the merge, the body left as galley reads it.
Whole pages win when the body has errors too, as Kadesh's small capitals
do ("Tue" for "The", "Breastep" for "Breasted").

A second reading by Qwen 3.6 27B of each note band would mark for review
the edits the two models disagree on: on the six pages it flags 24 of
the 35B model's 33 wrong note words and 9 right ones. It costs 28 s a
band, about 20 minutes for Kadesh. I recommend building it as an option
of the stage, off by default, since it flags but does not fix.

The combination of the text layer and Tesseract is not worth building:
it removes 2 wrong words in 100 in the notes (26.5 to 24.4), the model
23 (26.5 to 3.4).

What is not known:

- How the model does on other books. Kadesh is the only one of the
  eight books whose text layer is bad enough to need `ocr = "redo"`; on
  books printed and scanned better the gain may be small and the risk
  the same. The correct stage should be measured on one more book before
  `correct = true` is suggested for it.
- Whether the rates hold on Kadesh's other 38 text pages: six of its 44
  were measured.
- Whether 1 fluent wrong word in 300 is acceptable to the owner, against
  about 3 wrong words in 10 in Kadesh's blurred notes today. This is the
  owner's decision; the second reading above is the way to lower it.
- Whether another prompt or resolution does better: one prompt and 300
  dpi were tried for the Qwen models.

## For whoever builds the correct stage

- LM Studio takes `"reasoning_effort": "none"` in the chat completions
  request and then gives no reasoning: on a note band of page 9 the 35B
  model took 4.3 s without it and 13.5 s with it, which is the default.
  `chat_template_kwargs` and `reasoning: {effort}` had no effect.
- The scripts and every output are in `tmp/measure/` of the
  `plan/notes-vision` worktree, which git ignores: `common.py` (loading,
  word order, normalisation, alignment), `vision.py` (the requests),
  `baseline.py`, `combine.py`, `merge.py`, `score_vision.py`,
  `agree.py`, `edits.py` (the count of edits above), `final_table.py`. The reference is in `tmp/measure/ref/`;
  copy it to `tests/fixtures/expected/` if work package 4 scores against
  it.
- Words of the layer and of Tesseract were put in reading order by
  their boxes, with the page's slope taken out (page 27 slopes 1.2
  points in 100), body first, then the left note column, then the
  right. Sorting by box without the slope mixed the lines of page 11
  and raised Tesseract's error rate in the body from 2.0 to 11.3.
- olmOCR 2 7B stays on disk (6 GB); LM Studio's command `lms rm`
  removes it.
