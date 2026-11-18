"""The runs of a page's body stream that are blocks of their own (spec
section 2, step 2.3): its headings, the chapter summary under a heading,
the epigraphs under a chapter's heading and the runs of verse, found per
page before the paragraphs are made."""

from dataclasses import dataclass
from enum import StrEnum

from galley.model import BlockKind, WordChange

# Spec section 14, "Levels": a chapter's heading is level 1, a section's 2.
CHAPTER_LEVEL = 1
SECTION_LEVEL = 2


class LabelLine(StrEnum):
    """Whether a heading's first line is its chapter label, kept apart from
    the title the lines after it hold (spec section 14)."""

    FIRST = "first"
    NONE = "none"


class QuotationForm(StrEnum):
    """Whether an epigraph's quotation is prose, its lines joined as a
    paragraph's, or verse, its line breaks kept (spec section 22, "Verse")."""

    PROSE = "prose"
    VERSE = "verse"


@dataclass(frozen=True, slots=True, kw_only=True)
class EpigraphParts:
    """What an epigraph's run holds besides its lines (spec section 22,
    "The block"): how many of its first lines are the quotation, the rest
    being its source; the quotation's form; the source's words without
    the leading dash, joined by single spaces; and the record of that
    dash's removal, None when the source starts with none."""

    quotation_lines: int
    form: QuotationForm
    source: str
    source_dash: WordChange | None


@dataclass(frozen=True, slots=True, kw_only=True)
class BodyRun:
    """Lines of a page's body stream that are one block of `kind`: the
    position of the first and of the line after the last; a heading's
    `level` and `label_line`, whether its first line is its chapter label;
    an epigraph's `epigraph`, its quotation and source."""

    start: int
    end: int
    kind: BlockKind
    level: int | None = None
    label_line: LabelLine = LabelLine.NONE
    epigraph: EpigraphParts | None = None
