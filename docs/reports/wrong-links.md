# Report: fewer wrong note links, fewer notes joined

For the owner. Started on 24 November 2026, at main a908204. The plan is
`docs/plans/wrong-links.md`.

## Work package 2: unmarked notes and signs

Done (99848e6 spec, 9682a3b code). In books numbered per page, a
footnote with no marker, or a sign (`*`, `^`, `•`), is linked only
where the page expects it: the page's first note, or the note before it
linked. Domesday's wrong links on page indices 106, 200 and 499 (two)
are gone, each checked on the page image; Domesday links 1,589 → 1,585,
galley-eval's right count unchanged at 1,563; Haskins 68 right,
unchanged. Gierke, Kadesh (without the model), Stubbs, Turney and
Haynes: blocks.json byte-identical.

Still wrong: Domesday 154 and 498 (the sign sits where the order
expects a reference; the real one was read as a word or an amount),
Haskins 204 (the page's only note, two candidates, the earlier wins).

Changed from the plan: the rule is not applied to books numbered
through (Kadesh), where it unlinked 15 of 45 links, three of them right
by the spec's own record; and a sign may link the page's first note,
not only its only note, which keeps 6 right Haskins links.
