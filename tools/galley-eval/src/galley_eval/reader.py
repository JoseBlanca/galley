"""The reader of the reference text: a Gutenberg HTML edition read, by its
book's reading rules, into the things blocks.json holds (spec section 4).

It gives the body blocks in order, each with its kind; the notes in order,
each with its blocks; the note references, each with the note it points
to; and the page anchors, each with its printed page number. A note
reference and a page anchor sit in a gap between two tokens of a stream:
the body, which is every body block in order, margin notes, index entries
and tables included, or the notes, every note's blocks in order.

How the rules apply, beyond the spec's words:

- An element that a rule of the table matches wins over a paragraph that
  holds it: a `span.sidenote` inside a `p` is a margin note of its own,
  placed just before that paragraph, whose text runs on without it.
  Inside an element that a rule matches, the outermost wins.
- Any element other than `p` with text of its own is a paragraph, not
  only a `div`: text of its own is text outside its child elements other
  than inline ones (`span`, `i`, `a`, `sup`, ...). Inside an index, such an
  element, and every `li`, is an index entry.
- Text outside every block, such as text directly in `body`, and content
  of a notes section before its first note, are a ReferenceReadError, so
  that no word is lost unseen. Text that a misplaced end tag leaves
  between two elements of a notes section is a paragraph of the note
  before it.
- A page anchor or note reference inside a dropped element is dropped
  with it.
- Elements other than inline ones separate words, as `<br>` does.
"""

import re
from dataclasses import dataclass, replace
from enum import StrEnum
from html.parser import HTMLParser
from pathlib import Path
from typing import override

from galley_eval.errors import ReferenceReadError
from galley_eval.rules import ReadingRules, Selector, SimpleSelector

__all__ = [
    "Gap",
    "NoteReference",
    "PageAnchor",
    "ReferenceBlock",
    "ReferenceKind",
    "ReferenceNote",
    "ReferenceText",
    "ReferenceToken",
    "Stream",
    "read_reference",
    "read_reference_file",
]


class ReferenceKind(StrEnum):
    """What a block of the reference is: galley's block kinds, and tables."""

    HEADING = "heading"
    PARAGRAPH = "paragraph"
    QUOTE = "quote"
    FIGURE = "figure"
    MARGIN_NOTE = "margin_note"
    INDEX_ENTRY = "index_entry"
    TABLE = "table"


@dataclass(frozen=True, slots=True)
class ReferenceToken:
    """A word of the reference, split on white space, with Gutenberg's
    accents, quotes and dashes. `marked_correction` is true when some of
    its letters are inside a correction Gutenberg marked (`ins.correction`)."""

    text: str
    marked_correction: bool


@dataclass(frozen=True, slots=True)
class ReferenceBlock:
    """A block of the reference: its kind and its tokens, never none."""

    kind: ReferenceKind
    tokens: tuple[ReferenceToken, ...]


@dataclass(frozen=True, slots=True)
class ReferenceNote:
    """A note: the `id` its references point to, and its blocks."""

    note_id: str
    blocks: tuple[ReferenceBlock, ...]


class Stream(StrEnum):
    """The two sequences of tokens a gap is counted in."""

    BODY = "body"  # every body block in order
    NOTES = "notes"  # every note's blocks, the notes in order


@dataclass(frozen=True, slots=True)
class Gap:
    """The place just before the token at `token_index` of `stream`, the
    tokens counted from 0 through the stream; the stream's length is the
    place after its last token."""

    stream: Stream
    token_index: int


@dataclass(frozen=True, slots=True)
class NoteReference:
    """A note reference in the body: the `id` of its note and its place."""

    note_id: str
    gap: Gap


@dataclass(frozen=True, slots=True)
class PageAnchor:
    """Where a printed page starts: its number as printed, "47" or "vii",
    and its place. An anchor inside a word is placed after the word."""

    printed_page: str
    gap: Gap


@dataclass(frozen=True, slots=True, kw_only=True)
class ReferenceText:
    """A book's reference text (spec section 4)."""

    blocks: tuple[ReferenceBlock, ...]
    notes: tuple[ReferenceNote, ...]
    note_references: tuple[NoteReference, ...]
    page_anchors: tuple[PageAnchor, ...]


def read_reference_file(path: Path, rules: ReadingRules) -> ReferenceText:
    """The reference text of the Gutenberg HTML file at `path`, read by
    `rules`. Raises ReferenceReadError as read_reference does, with the
    file's path in the message."""
    html = path.read_text(encoding="utf-8")
    try:
        return read_reference(html, rules)
    except ReferenceReadError as err:
        message = f"{path}: {err}"
        raise ReferenceReadError(message) from err


def read_reference(html: str, rules: ReadingRules) -> ReferenceText:
    """The reference text of the Gutenberg HTML `html`, read by `rules`.

    Raises ReferenceReadError when no element matches `start` (or there is
    no `header.pg-boilerplate` when `start` is empty), when text lies
    outside every block, when a notes section has content before its first
    note, when a note holds no `id` that a note reference points to, or
    when a page anchor has neither an `id="Page_N"` nor a `title`.
    """
    root = _from_start(_tree(_events(html)), rules)
    context = _Context(
        rules=rules,
        targets=_note_targets(root, rules),
        in_note=False,
        in_index=False,
        correction=False,
    )
    return _assemble(_container(root.children, root, context))


# The HTML tree


@dataclass(frozen=True, slots=True)
class _Element:
    tag: str
    attributes: frozendict[str, str]
    classes: frozenset[str]
    children: tuple[_Element | str, ...]


@dataclass(frozen=True, slots=True)
class _StartTag:
    tag: str
    attributes: frozendict[str, str]


@dataclass(frozen=True, slots=True)
class _EndTag:
    tag: str


type _Event = _StartTag | _EndTag | str

_VOID_TAGS = frozenset(
    ("area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta")
    + ("param", "source", "track", "wbr")
)


def _events(html: str) -> tuple[_Event, ...]:
    """The start tags, end tags and text of `html`, in order, character
    references decoded. html.parser hands them to methods of a subclass;
    the subclass lives only in this call."""
    events: list[_Event] = []

    class _Collector(HTMLParser):
        @override
        def handle_starttag(
            self, tag: str, attrs: list[tuple[str, str | None]]
        ) -> None:
            attributes = frozendict({name: value or "" for name, value in attrs})
            events.append(_StartTag(tag, attributes))

        @override
        def handle_startendtag(
            self, tag: str, attrs: list[tuple[str, str | None]]
        ) -> None:
            self.handle_starttag(tag, attrs)
            if tag not in _VOID_TAGS:
                events.append(_EndTag(tag))

        @override
        def handle_endtag(self, tag: str) -> None:
            events.append(_EndTag(tag))

        @override
        def handle_data(self, data: str) -> None:
            events.append(data)

    collector = _Collector(convert_charrefs=True)
    collector.feed(html)
    collector.close()
    return tuple(events)


@dataclass(slots=True)
class _Open:
    """An element whose end tag has not come yet. Mutable, and used only
    inside _tree, which freezes it into an _Element when it closes."""

    tag: str
    attributes: frozendict[str, str]
    children: list[_Element | str]


def _tree(events: tuple[_Event, ...]) -> _Element:
    """The tree of `events` under a root element `#document`. A void
    element has no children; an end tag closes the elements opened after
    its own start tag. An end tag with no open element of its tag is a
    ReferenceReadError."""
    stack = [_Open("#document", frozendict(), [])]
    for event in events:
        match event:
            case str():
                stack[-1].children.append(event)
            case _StartTag(tag=tag, attributes=attributes):
                if tag in _VOID_TAGS:
                    stack[-1].children.append(_element(_Open(tag, attributes, [])))
                else:
                    stack.append(_Open(tag, attributes, []))
            case _EndTag(tag=tag):
                if tag in _VOID_TAGS:
                    continue  # `</br>` and the like close nothing
                open_tags = [opened.tag for opened in stack]
                if tag not in open_tags[1:]:
                    message = f"the end tag </{tag}> closes no open element"
                    raise ReferenceReadError(message)
                while True:
                    closed = stack.pop()
                    stack[-1].children.append(_element(closed))
                    if closed.tag == tag:
                        break
            case _:
                raise AssertionError(event)
    while len(stack) > 1:
        closed = stack.pop()
        stack[-1].children.append(_element(closed))
    return _element(stack[0])


def _element(opened: _Open) -> _Element:
    return _Element(
        tag=opened.tag,
        attributes=opened.attributes,
        classes=frozenset(opened.attributes.get("class", "").split()),
        children=tuple(opened.children),
    )


def _simple_matches(simple: SimpleSelector, element: _Element) -> bool:
    return (simple.tag is None or simple.tag == element.tag) and (
        simple.class_name is None or simple.class_name in element.classes
    )


def _matches(
    selectors: tuple[Selector, ...], element: _Element, parent: _Element
) -> bool:
    return any(
        _simple_matches(selector.element, element)
        and (selector.parent is None or _simple_matches(selector.parent, parent))
        for selector in selectors
    )


_GUTENBERG_HEADER = (
    Selector(
        text="header.pg-boilerplate",
        element=SimpleSelector(tag="header", class_name="pg-boilerplate"),
        parent=None,
    ),
)


def _from_start(root: _Element, rules: ReadingRules) -> _Element:
    """`root` without what comes before the start: before the first element
    that `rules.start` matches, or up to and including Gutenberg's header
    when `rules.start` is empty."""
    if len(rules.start) > 0:
        pruned = _prune(root, rules.start, keep_match=True)
        wanted = ", ".join(selector.text for selector in rules.start)
    else:
        pruned = _prune(root, _GUTENBERG_HEADER, keep_match=False)
        wanted = "header.pg-boilerplate"
    if pruned is None:
        message = f"no element matches the start rule ({wanted})"
        raise ReferenceReadError(message)
    return pruned


def _prune(
    element: _Element, selectors: tuple[Selector, ...], *, keep_match: bool
) -> _Element | None:
    """`element` keeping only what follows the first descendant that
    `selectors` match, that descendant too when `keep_match` is true; None
    when no descendant matches."""
    for position, child in enumerate(element.children):
        if isinstance(child, str):
            continue
        after = element.children[position + 1 :]
        if _matches(selectors, child, element):
            kept = (child, *after) if keep_match else after
            return replace(element, children=kept)
        inner = _prune(child, selectors, keep_match=keep_match)
        if inner is not None:
            return replace(element, children=(inner, *after))
    return None


def _note_targets(root: _Element, rules: ReadingRules) -> frozenset[str]:
    """The `id`s that the `href` of some `a` matching `note_reference`
    points to, anywhere under `root`."""
    targets: set[str] = set()
    pending = [root]
    while pending:
        element = pending.pop()
        if _is_note_link(element, rules):
            targets.add(element.attributes["href"].removeprefix("#"))
        pending.extend(
            child for child in element.children if isinstance(child, _Element)
        )
    return frozenset(targets)


def _is_note_link(element: _Element, rules: ReadingRules) -> bool:
    href = element.attributes.get("href")
    return (
        element.tag == "a"
        and href is not None
        and any(pattern.fullmatch(href) for pattern in rules.note_reference)
    )


# Walking the tree into raw blocks and notes


@dataclass(frozen=True, slots=True, kw_only=True)
class _Context:
    rules: ReadingRules
    targets: frozenset[str]
    in_note: bool  # note references are cross-references here
    in_index: bool  # a block is an index entry here
    correction: bool  # inside `ins.correction`


@dataclass(frozen=True, slots=True)
class _Anchor:
    printed_page: str


@dataclass(frozen=True, slots=True)
class _Reference:
    note_id: str


type _Marker = _Anchor | _Reference


@dataclass(frozen=True, slots=True)
class _Text:
    text: str
    correction: bool


@dataclass(frozen=True, slots=True)
class _Lifted:
    element: _Element
    parent: _Element


type _Piece = _Text | _Anchor | _Reference | _Lifted


@dataclass(frozen=True, slots=True)
class _RawBlock:
    """A block before its tokens are counted in a stream: its text, the
    character ranges of marked corrections, and its markers at character
    offsets. `kind` is None for markers that sit between blocks."""

    kind: ReferenceKind | None
    text: str
    corrections: tuple[tuple[int, int], ...]
    markers: tuple[tuple[int, _Marker], ...]


@dataclass(frozen=True, slots=True)
class _RawNote:
    note_id: str
    blocks: tuple[_RawBlock, ...]


type _Item = _RawBlock | _RawNote

# Elements whose text runs on into the text around them. Every other
# element separates words.
_INLINE_TAGS = frozenset(
    ("a", "abbr", "b", "bdi", "bdo", "big", "cite", "code", "del", "dfn", "em")
    + ("font", "i", "ins", "kbd", "mark", "q", "s", "samp", "small", "span")
    + ("strong", "sub", "sup", "time", "tt", "u", "var")
)
_CORRECTION = (
    Selector(
        text="ins.correction",
        element=SimpleSelector(tag="ins", class_name="correction"),
        parent=None,
    ),
)
_SPACE = _Text(" ", correction=False)
# Never a block, so that text directly in them is an error, not a paragraph
# as long as the book.
_DOCUMENT_TAGS = frozenset(("html", "body"))


def _block_kind(
    element: _Element, parent: _Element, rules: ReadingRules
) -> ReferenceKind | None:
    """The kind of block a rule of the table makes of `element`, or None."""
    for selectors, kind in (
        (rules.margin_note, ReferenceKind.MARGIN_NOTE),
        (rules.table, ReferenceKind.TABLE),
        (rules.figure, ReferenceKind.FIGURE),
        (rules.quote, ReferenceKind.QUOTE),
        (rules.heading, ReferenceKind.HEADING),
    ):
        if _matches(selectors, element, parent):
            return kind
    return None


def _is_rule_block(element: _Element, parent: _Element, rules: ReadingRules) -> bool:
    return (
        _block_kind(element, parent, rules) is not None
        or _matches(rules.note, element, parent)
        or _matches(rules.notes_section, element, parent)
        or _matches(rules.index, element, parent)
    )


def _is_dropped_text(text: str, rules: ReadingRules) -> bool:
    stripped = text.strip()
    return stripped == "" or any(
        pattern.fullmatch(stripped) for pattern in rules.drop_text
    )


def _container(
    children: tuple[_Element | str, ...], parent: _Element, context: _Context
) -> tuple[_Item, ...]:
    """The blocks and notes of `children` of `parent`, an element that is
    no block itself, in document order."""
    rules = context.rules
    items: list[_Item] = []
    for child in children:
        if isinstance(child, str):
            if not _is_dropped_text(child, rules):
                message = f"text outside every block, in <{parent.tag}>: {child.strip()[:80]!r}"
                raise ReferenceReadError(message)
            continue
        if _matches(rules.drop, child, parent):
            continue
        marker = _marker(child, parent, context)
        if marker is not None:
            items.append(_RawBlock(None, "", (), ((0, marker),)))
        elif _matches(rules.notes_section, child, parent) and not context.in_note:
            items.extend(_notes_section(child, context))
        elif _matches(rules.note, child, parent) and not context.in_note:
            items.append(_rule_note(child, context))
        elif _matches(rules.index, child, parent):
            index_context = replace(context, in_index=True)
            items.extend(_container(child.children, child, index_context))
        elif (kind := _block_kind(child, parent, rules)) is not None:
            items.extend(_block(kind, child, context, lift=False))
        elif child.tag not in _DOCUMENT_TAGS and (
            child.tag == "p"
            or (context.in_index and child.tag == "li")
            or _has_own_text(child, context)
        ):
            kind = (
                ReferenceKind.INDEX_ENTRY
                if context.in_index
                else ReferenceKind.PARAGRAPH
            )
            items.extend(_block(kind, child, context, lift=True))
        else:
            items.extend(_container(child.children, child, context))
    return tuple(items)


def _marker(element: _Element, parent: _Element, context: _Context) -> _Marker | None:
    """The page anchor or note reference that `element` is, or None."""
    if _matches(context.rules.page_anchor, element, parent):
        return _Anchor(_printed_page(element))
    if not context.in_note and _is_note_link(element, context.rules):
        return _Reference(element.attributes["href"].removeprefix("#"))
    return None


_PAGE_ID_PREFIX = "Page_"


def _printed_page(element: _Element) -> str:
    """The printed page number of a page anchor: from `id="Page_N"`, else
    from its `title`."""
    element_id = element.attributes.get("id", "")
    if element_id.startswith(_PAGE_ID_PREFIX) and element_id != _PAGE_ID_PREFIX:
        return element_id.removeprefix(_PAGE_ID_PREFIX)
    title = element.attributes.get("title", "").strip()
    if title == "":
        message = f"a page anchor <{element.tag}> has neither id=Page_N nor a title"
        raise ReferenceReadError(message)
    return title


def _has_own_text(element: _Element, context: _Context) -> bool:
    """Whether `element` holds a word outside its child elements other
    than inline ones, leaving out what is dropped and the text of page
    anchors and note references."""
    rules = context.rules
    for child in element.children:
        if isinstance(child, str):
            if not _is_dropped_text(child, rules):
                return True
        elif (
            child.tag in _INLINE_TAGS
            and not _matches(rules.drop, child, element)
            and _marker(child, element, context) is None
            and not _is_rule_block(child, element, rules)
            and _has_own_text(child, context)
        ):
            return True
    return False


def _block(
    kind: ReferenceKind, element: _Element, context: _Context, *, lift: bool
) -> tuple[_Item, ...]:
    """The block of `kind` that `element` owns. With `lift`, an element
    inside it that a rule matches is taken out as a block or note of its
    own, placed before this one."""
    pieces = _pieces(element, context, lift=lift)
    lifted = tuple(
        item
        for piece in pieces
        if isinstance(piece, _Lifted)
        for item in _container((piece.element,), piece.parent, context)
    )
    return (*lifted, _raw_block(kind, pieces))


def _pieces(element: _Element, context: _Context, *, lift: bool) -> tuple[_Piece, ...]:
    """The text, markers and lifted elements inside `element`, in order."""
    rules = context.rules
    pieces: list[_Piece] = []
    for child in element.children:
        if isinstance(child, str):
            if not any(pattern.fullmatch(child.strip()) for pattern in rules.drop_text):
                pieces.append(_Text(child, context.correction))
            continue
        if _matches(rules.drop, child, element):
            continue
        marker = _marker(child, element, context)
        if marker is not None:
            pieces.append(marker)
        elif lift and _is_rule_block(child, element, rules):
            pieces.append(_Lifted(child, element))
        elif child.tag == "br":
            pieces.append(_SPACE)
        else:
            inner_context = (
                replace(context, correction=True)
                if _matches(_CORRECTION, child, element)
                else context
            )
            inner = _pieces(child, inner_context, lift=lift)
            if child.tag in _INLINE_TAGS and not _matches(
                rules.separate, child, element
            ):
                pieces.extend(inner)
            else:
                pieces.extend((_SPACE, *inner, _SPACE))
    return tuple(pieces)


def _raw_block(kind: ReferenceKind, pieces: tuple[_Piece, ...]) -> _RawBlock:
    text_parts: list[str] = []
    corrections: list[tuple[int, int]] = []
    markers: list[tuple[int, _Marker]] = []
    length = 0
    for piece in pieces:
        match piece:
            case _Text(text=text, correction=correction):
                if correction:
                    corrections.append((length, length + len(text)))
                text_parts.append(text)
                length += len(text)
            case _Anchor() | _Reference():
                markers.append((length, piece))
            case _Lifted():
                text_parts.append(" ")
                length += 1
            case _:
                raise AssertionError(piece)
    return _RawBlock(kind, "".join(text_parts), tuple(corrections), tuple(markers))


def _notes_section(section: _Element, context: _Context) -> tuple[_Item, ...]:
    """The notes of a notes section. With `note` rules, the notes they
    match; without, a note starts at each child element that holds an `id`
    a note reference points to, and what follows it, up to the next such,
    continues it: elements, and text left between elements by a misplaced
    end tag (Domesday's note 101 ends `</p>.’]`)."""
    if len(context.rules.note) > 0:
        return _container(section.children, section, context)
    groups: list[list[_Element | str]] = []
    for child in section.children:
        if isinstance(child, _Element) and _note_id(child, context.targets) is not None:
            groups.append([child])
        elif isinstance(child, str) and _is_dropped_text(child, context.rules):
            continue
        elif len(groups) > 0:
            groups[-1].append(child)
        elif isinstance(child, str) or not _matches(context.rules.drop, child, section):
            message = (
                "a notes section holds content before its first note, an "
                f"element with an id that a note reference points to: {child!r:.80}"
            )
            raise ReferenceReadError(message)
    return tuple(_grouped_note(section, tuple(group), context) for group in groups)


def _rule_note(element: _Element, context: _Context) -> _RawNote:
    """The note that `element`, matched by a `note` rule, is."""
    note_id = _note_id(element, context.targets)
    if note_id is None:
        message = f"a note <{element.tag}> holds no id that a note reference points to"
        raise ReferenceReadError(message)
    note_context = replace(context, in_note=True)
    if _has_own_text(element, note_context):
        items = _block(ReferenceKind.PARAGRAPH, element, note_context, lift=False)
    else:
        items = _container(element.children, element, note_context)
    return _raw_note(note_id, items)


def _grouped_note(
    section: _Element, group: tuple[_Element | str, ...], context: _Context
) -> _RawNote:
    """The note made of `group`, consecutive children of a notes section,
    the first an element with the note's id. A text among them is a
    paragraph of the note."""
    first = group[0]
    note_id = None if isinstance(first, str) else _note_id(first, context.targets)
    if note_id is None:
        raise AssertionError(first)  # a group starts at an element with one
    note_context = replace(context, in_note=True)
    items = tuple(
        item
        for child in group
        for item in (
            (_raw_block(ReferenceKind.PARAGRAPH, (_Text(child, correction=False),)),)
            if isinstance(child, str)
            else _container((child,), section, note_context)
        )
    )
    return _raw_note(note_id, items)


def _raw_note(note_id: str, items: tuple[_Item, ...]) -> _RawNote:
    blocks = tuple(item for item in items if isinstance(item, _RawBlock))
    if len(blocks) != len(items):
        message = f"note {note_id} holds another note"
        raise ReferenceReadError(message)
    return _RawNote(note_id, blocks)


def _note_id(element: _Element, targets: frozenset[str]) -> str | None:
    """The first `id` in `targets` on `element` or inside it, dropped
    elements included, in document order."""
    element_id = element.attributes.get("id")
    if element_id is not None and element_id in targets:
        return element_id
    for child in element.children:
        if isinstance(child, _Element):
            found = _note_id(child, targets)
            if found is not None:
                return found
    return None


# Counting the tokens in their streams

_WORD = re.compile(r"\S+")


def _tokens(
    block: _RawBlock,
) -> tuple[tuple[ReferenceToken, ...], tuple[tuple[int, _Marker], ...]]:
    """The tokens of `block` and its markers at the index of the token they
    come before, a marker inside a word coming after it."""
    spans = tuple((match.start(), match.end()) for match in _WORD.finditer(block.text))
    tokens = tuple(
        ReferenceToken(
            block.text[start:end],
            marked_correction=any(
                low < end and start < high for low, high in block.corrections
            ),
        )
        for start, end in spans
    )
    markers = tuple(
        (sum(1 for start, _ in spans if start < offset), marker)
        for offset, marker in block.markers
    )
    return tokens, markers


def _assemble(items: tuple[_Item, ...]) -> ReferenceText:
    blocks: list[ReferenceBlock] = []
    notes: list[ReferenceNote] = []
    references: list[NoteReference] = []
    anchors: list[PageAnchor] = []
    counts = {Stream.BODY: 0, Stream.NOTES: 0}

    def place(raw: _RawBlock, stream: Stream) -> ReferenceBlock | None:
        tokens, markers = _tokens(raw)
        for index, marker in markers:
            gap = Gap(stream, counts[stream] + index)
            match marker:
                case _Anchor(printed_page=printed_page):
                    anchors.append(PageAnchor(printed_page, gap))
                case _Reference(note_id=note_id):
                    references.append(NoteReference(note_id, gap))
        counts[stream] += len(tokens)
        if raw.kind is None or len(tokens) == 0:
            return None
        return ReferenceBlock(raw.kind, tokens)

    for item in items:
        match item:
            case _RawBlock():
                block = place(item, Stream.BODY)
                if block is not None:
                    blocks.append(block)
            case _RawNote(note_id=note_id, blocks=raw_blocks):
                placed = (place(raw, Stream.NOTES) for raw in raw_blocks)
                notes.append(
                    ReferenceNote(
                        note_id, tuple(block for block in placed if block is not None)
                    )
                )
    return ReferenceText(
        blocks=tuple(blocks),
        notes=tuple(notes),
        note_references=tuple(references),
        page_anchors=tuple(anchors),
    )
