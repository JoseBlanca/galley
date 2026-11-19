# Plan: paragraphs cut by notes, and a local vision model

This plan does three things the owner asked for on 19 November 2026,
after reading the EPUBs of the ocr-redo plan:

- **Paragraphs no longer cut by unlinked notes.** When a note's
  marker is not linked, galley shows the note where it was printed, at
  the foot of its page, so a paragraph that runs on to the next page is
  cut in two with the notes between ("…exhaustively collated with the"
  / notes / "original of the Sallier Papyrus…", Kadesh
  `battleofkadeshst00breauoft`, pages 11 and 12). This holds for every
  book; Kadesh has 142 unlinked notes. The owner called it "a serious
  real problem".
- **A measurement of the ways to read bad print better**, before any of
  them is built: combining the readings galley has (the scan's text
  layer, Tesseract), and a local vision model run through LM Studio,
  which the owner uses (`http://localhost:1234`, an OpenAI-compatible
  server). The owner allowed downloading models.
- **The correct stage**, optional (`correct = true` in `book.toml`,
  already in the config and the architecture, never built), built from
  what the measurement shows, with each change logged as an edit.

And two Stubbs faults (`earlyplantagenet01stub`): "aggres* sive", a
speck read as "*" at a line-end hyphen so the halves do not join, and
"p by 5*invasion", words of a margin note left in a body line.

The owner said to go on without waiting. Dated 19 November 2026.
State: approved; under way.

Page means page index of the whole PDF, from 0.

## In and out

In: the paragraph fix in structure (or markdown, where the spec puts
it) for every book; the two Stubbs faults; the measurement (work
package 2) and its report; the spec of the correct stage from that
report (`docs/specs/correct.md`), and the stage itself, off by default.

Out: a cloud model (book text never leaves the machine); training a
model; Mariéjol; Kadesh's page 27 sloping line.

Known before the plan: Kadesh's notes are blurred on the scan itself
(page 11 rendered at 300, 450 and 600 dpi gives Tesseract the same
misreadings), so a sharper render does not help. LM Studio has two
vision models already: Qwen 3.6 27B and Qwen 3.6 35B-A3B; the machine
is an Apple M5 Pro with 64 GB.

What decides the shape of work packages 3 and 4 is work package 2's
result. If no way beats the current reading by a clear margin on the
measured pages, work package 3 writes that in the spec and work package
4 is not built; the plan says so in the report and stops.

## The order of the work, and the streams

Work packages 1 and 2 run side by side: 1 changes `src/galley/structure/`
(and markdown if the spec puts the fix there) and their tests; 2 writes
only under `tmp/` and its report, `docs/reports/notes-vision-measure.md`.
Work packages 3 and 4 follow 2.

## 1. Paragraphs cut by unlinked notes, and Stubbs

Deliverables:

1. A spec amendment (structure, where paragraphs are joined across a
   page break and where unlinked notes are placed): a paragraph that
   runs on to the next page is joined whatever unlinked notes stand
   between, and the notes follow the joined paragraph. Check: the
   `first-reader` and `spec-reviewer` subagents.
2. Excerpt tests: Kadesh pages 11 and 12 (`kadesh_redo`) give one
   paragraph "…collated with the original of the Sallier Papyrus…", with
   the page's notes after it; the same on a page of another book where
   a paragraph runs over notes (found by the task). They fail first.
3. Whole books: the count of paragraphs ending without closing
   punctuation right before a note block, by book, before and after;
   after, near 0 on every book; each remaining case looked at.
4. Stubbs: "aggressive" whole and "David had … by invasion" without
   the margin note's words; spec first; tests on those lines.

Tasks:

- [ ] 1.1 The spec amendments of deliverables 1 and 4.
- [ ] 1.2 The paragraph fix, deliverables 2 and 3.
- [ ] 1.3 The Stubbs faults, deliverable 4.
- [ ] Review of work package 1.

## 2. The measurement

Deliverables, in `docs/reports/notes-vision-measure.md`:

1. A reference: 6 Kadesh pages (body, blurred notes, a page with
   hieroglyphs, a map caption; among them 8, 9, 11) transcribed from the
   page images by the assistant, word by word, kept under `tmp/` (and
   in `tests/fixtures/expected/` if work package 4 needs them).
2. Word error rate against it, for the body and the notes apart, of:
   the scan's text layer; Tesseract; galley's current redo output;
   an oracle that picks, per aligned word, any reading that is right
   (the most combining could gain); a simple combination (dictionary
   word first, then confidence); and two or three vision models through
   LM Studio, given the page image or the note band, asked for a
   transcription. One model trained for OCR may be downloaded with
   `lms get`.
3. Invented text: words a vision model gives that are not on the page,
   counted apart, since a fluent invented word is worse than visible
   junk.
4. Time per page and per note band, for each model.
5. A recommendation for work packages 3 and 4: which model, read what
   (whole page, note bands, low-confidence lines), and how its text is
   merged with galley's words (only where it aligns), with the numbers.

Tasks:

- [ ] 2.1 The reference transcription.
- [ ] 2.2 The measurement and the report.

## 3. The spec of the correct stage

From the report of work package 2: `docs/specs/correct.md`, and the
architecture's parts on correct (its edits file, the config key, the
model's address and name in the config, how it is called, what it reads,
what an edit records, how markdown applies it). Check: the
`first-reader` and `spec-reviewer` subagents.

- [ ] 3.1 The spec.

## 4. The correct stage

Deliverables:

1. `galley2epub correct <book folder>` writes `edits/correct.jsonl`;
   markdown applies it; `run` runs it when `correct = true`. Without LM
   Studio running, correct stops with a message that says so.
2. Unit tests with the model's answers recorded (no model in the quick
   tests); one test marked `vision_model`, excluded by default, that
   calls LM Studio on a Kadesh page.
3. Kadesh with `correct = true`: word error rate on the reference pages
   against work package 2's numbers, invented words counted.

- [ ] 4.1 The stage and its tests.
- [ ] 4.2 Kadesh measured with it.
- [ ] Review of work packages 3 and 4.

## 5. The EPUBs

- [ ] 5.1 All checks, `pytest -m whole_book`, the evaluation against
  `runs/ocr-redo-final/`, the seven EPUBs in `runs/notes-vision/`
  through epubcheck, Kadesh with and without `correct`.
- [ ] 5.2 The pages of each change checked by eye.
