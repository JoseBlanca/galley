"""The runs of a page's body stream that are blocks of their own (spec
section 2, step 2.3): its headings, the chapter summary under a heading and
the runs of verse, found per page before the paragraphs are made."""

from dataclasses import dataclass
from enum import StrEnum

from galley.model import BlockKind


class Label(StrEnum):
    """Whether a heading's first line is its chapter label, kept apart from
    the title the lines after it hold (spec section 14)."""

    FIRST_LINE = "first_line"
    NONE = "none"


@dataclass(frozen=True, slots=True, kw_only=True)
class BodyRun:
    """Lines of a page's body stream that are one block of `kind`: the
    position of the first and of the line after the last; a heading's
    `level` and `label`."""

    start: int
    end: int
    kind: BlockKind
    level: int | None = None
    label: Label = Label.NONE
