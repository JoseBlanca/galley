# Report: paragraphs cut by notes, and a local vision model

The work report of `docs/plans/notes-vision.md`, for the owner. Started on
19 November 2026, at main df72ba4.

## Work package 2: the measurement

Done; the report is `docs/reports/notes-vision-measure.md` (c501378).
On 6 Kadesh pages transcribed by eye (1,975 body words, 1,356 note
words), wrong words per 100: galley with redo 2.0 in the body and 26.5
in the notes; the best any combination of the text layer and Tesseract
could do, 0.5 and 12.3, and a simple combination 1.4 and 24.4; the
vision model Qwen 3.6 35B-A3B reading the whole page 0.9 and 2.8, in
12.8 s a page, and merged with galley's words 0.7 and 3.4. Its risk:
about 1 word in 300 is wrong but looks right ("Borchardt" for
"Brugsch"). Combining the layer and Tesseract is not built; work
packages 3 and 4 build the correct stage with that model, reading whole
pages, merged word by word, off by default.
