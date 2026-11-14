"""The exceptions galley raises: GalleyError and one subclass per kind of failure.

A caller that wants to handle one kind of failure catches its subclass; the
command catches GalleyError to report any of them. The message of each says
which file, page or value was at fault.
"""

from enum import StrEnum


class GalleyError(Exception):
    """Any failure galley reports; a subclass says what kind."""


class ConfigError(GalleyError):
    """`book.toml` is missing, is not valid TOML, or has a wrong key or value."""


class InputFileError(GalleyError):
    """A file a stage reads is missing, malformed, of another format version,
    or made from another PDF."""


class PdfError(GalleyError):
    """The PDF cannot be read as the config asks, such as a page without text
    that the config does not exclude."""


class ExternalProgramError(GalleyError):
    """Tesseract or Pandoc is missing, or it failed."""


class EditError(GalleyError):
    """An edits file has a malformed line, or an edit does not apply."""


def _word_counts(counts: frozendict[str, int]) -> str:
    return ", ".join(f"{word!r} ({count})" for word, count in sorted(counts.items()))


class FidelityBoundary(StrEnum):
    """The stage boundaries where the fidelity check runs: words.json against
    lines.json (layout), lines.json against blocks.json (structure),
    blocks.json against book.md (markdown)."""

    LAYOUT = "layout"
    STRUCTURE = "structure"
    MARKDOWN = "markdown"


class FidelityError(GalleyError):
    """The words of a stage's output are not those of its input plus its
    removals: some are missing, some invented, or both.

    `boundary` is where the check ran. `missing` maps a word
    to how many times it is missing from the output, `invented` to how many
    times it is extra in it. `detail` is the rest of the message (pages,
    note counts). All four are kept as attributes so that a test can assert
    on them.
    """

    def __init__(
        self,
        boundary: FidelityBoundary,
        missing: frozendict[str, int],
        invented: frozendict[str, int],
        detail: str,
    ) -> None:
        self.boundary = boundary
        self.missing = missing
        self.invented = invented
        self.detail = detail
        message = (
            f"the fidelity check failed at the {boundary.value} boundary; "
            f"missing from the output: {_word_counts(missing) or 'none'}; "
            f"invented in the output: {_word_counts(invented) or 'none'}; "
            f"{detail}"
        )
        super().__init__(message)
