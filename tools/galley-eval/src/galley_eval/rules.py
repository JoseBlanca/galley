"""The reading rules of a book: which elements of its Gutenberg HTML are
what (spec section 4, "The rules").

A rule is a list of selectors, or of regular expressions for `drop_text`
and `note_reference`. Each rule has defaults, those of the spec's table;
a book's entry in `evaluation/books.toml` adds to them or replaces them.
"""

import re
from dataclasses import dataclass, fields, replace
from enum import StrEnum
from typing import cast

__all__ = [
    "DEFAULT_RULES",
    "RULE_NAMES",
    "ReadingRules",
    "RuleChange",
    "Selector",
    "SimpleSelector",
    "change_rules",
    "parse_selector",
]


@dataclass(frozen=True, slots=True)
class SimpleSelector:
    """`tag.class`, `tag` or `.class`: an element of that tag, or that has
    that class among its classes, or both. None where the selector does not
    name one."""

    tag: str | None
    class_name: str | None


@dataclass(frozen=True, slots=True)
class Selector:
    """A selector as the rules write it: one simple selector, or two joined
    by `>`, the element and its parent. `parent` is None for one. `text` is
    the selector as written, for messages."""

    text: str
    element: SimpleSelector
    parent: SimpleSelector | None


_SIMPLE = r"(?:[a-z][a-z0-9]*(?:\.[A-Za-z_][\w-]*)?|\.[A-Za-z_][\w-]*)"
_SELECTOR = re.compile(rf"({_SIMPLE})(?:\s*>\s*({_SIMPLE}))?")


def _simple(text: str) -> SimpleSelector:
    tag, _, class_name = text.partition(".")
    return SimpleSelector(tag=tag or None, class_name=class_name or None)


def parse_selector(text: str) -> Selector:
    """The selector written as `text`: `tag.class`, `tag`, `.class`, or two
    of these joined by `>` for a child. Raises ValueError for anything else,
    such as an `#id` or two classes."""
    match = _SELECTOR.fullmatch(text.strip())
    if match is None:
        message = (
            f"{text!r} is not a selector of the form tag.class, tag, .class, "
            "or two of these joined by >"
        )
        raise ValueError(message)
    first, second = match.group(1), match.group(2)
    if second is None:
        return Selector(text=text, element=_simple(first), parent=None)
    return Selector(text=text, element=_simple(second), parent=_simple(first))


@dataclass(frozen=True, slots=True, kw_only=True)
class ReadingRules:
    """The rules of spec section 4 for one book.

    An empty `start` means that reading starts at the first element after
    Gutenberg's header, `header.pg-boilerplate`. `drop_text` holds regular
    expressions that must match a whole run of text, its white space at
    both ends aside; `note_reference` holds regular expressions that must
    match the whole `href` of an `a`.
    """

    start: tuple[Selector, ...]
    drop: tuple[Selector, ...]
    drop_text: tuple[re.Pattern[str], ...]
    page_anchor: tuple[Selector, ...]
    heading: tuple[Selector, ...]
    margin_note: tuple[Selector, ...]
    notes_section: tuple[Selector, ...]
    note: tuple[Selector, ...]
    note_reference: tuple[re.Pattern[str], ...]
    quote: tuple[Selector, ...]
    index: tuple[Selector, ...]
    figure: tuple[Selector, ...]
    table: tuple[Selector, ...]


def _selectors(*texts: str) -> tuple[Selector, ...]:
    return tuple(parse_selector(text) for text in texts)


# The defaults of the table of spec section 4.
DEFAULT_RULES = ReadingRules(
    start=(),
    drop=_selectors(
        "footer.pg-boilerplate",
        "div.transnote",
        ".footnotes > h2",
        "a.label",
        "span.label",
    ),
    drop_text=(),
    page_anchor=_selectors("span.pagenum", "a.pagenum"),
    heading=_selectors("h1", "h2", "h3", "h4", "h5", "h6"),
    margin_note=_selectors("div.sidenote", "p.sidenote", "span.sidenote"),
    notes_section=(),
    note=(),
    note_reference=(re.compile(r"#Footnote_\d+"),),
    quote=_selectors(
        "div.blockquot", "div.quote", "p.quote", "div.poem", "div.poetry", "div.verse"
    ),
    index=_selectors("div.index", "ul.index", "ul.IX"),
    figure=_selectors("figure", "div.figcenter"),
    table=_selectors("table"),
)

RULE_NAMES = tuple(field.name for field in fields(ReadingRules))
_PATTERN_RULES = ("drop_text", "note_reference")


class RuleChange(StrEnum):
    """How a book's entry changes a rule's defaults."""

    ADD = "add"  # the book's values after the defaults
    REPLACE = "replace"  # the book's values instead of the defaults


def change_rules(
    rules: ReadingRules, change: RuleChange, rule: str, values: tuple[str, ...]
) -> ReadingRules:
    """`rules` with the rule named `rule` added to or replaced by `values`,
    written as in books.toml: selectors, or regular expressions for
    `drop_text` and `note_reference`. Raises ValueError for an unknown rule, a selector that does not parse or a
    regular expression that does not compile; the reader of books.toml
    turns it into a BooksFileError that names the file and the key."""
    if rule not in RULE_NAMES:
        message = f"unknown rule {rule!r}; the rules are {', '.join(RULE_NAMES)}"
        raise ValueError(message)
    if rule in _PATTERN_RULES:
        new: tuple[object, ...] = tuple(_pattern(value) for value in values)
    else:
        new = tuple(parse_selector(value) for value in values)
    # `rule` is one of the fields, checked above.
    old = cast("tuple[object, ...]", getattr(rules, rule))
    combined = (*old, *new) if change is RuleChange.ADD else new
    return replace(rules, **{rule: combined})


def _pattern(text: str) -> re.Pattern[str]:
    try:
        return re.compile(text)
    except re.error as err:
        message = f"{text!r} is not a regular expression: {err}"
        raise ValueError(message) from err
