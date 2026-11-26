"""The exceptions galley-eval raises: EvaluationError and one subclass per
kind of failure. The message of each says which file, book or value was at
fault."""


class EvaluationError(Exception):
    """Any failure galley-eval reports; a subclass says what kind."""


class BooksFileError(EvaluationError):
    """`evaluation/books.toml` is missing, is not valid TOML, or has a wrong
    key or value."""


class ReferenceReadError(EvaluationError):
    """A Gutenberg HTML edition cannot be read by its book's reading rules:
    the `start` element is missing, text lies outside every block, or a note
    has no `id` that a note reference points to."""


class AlignmentError(EvaluationError):
    """galley's words of a book align less than half of the reference's
    tokens to a token with the same key: a wrong scan or a broken reading
    rule is likelier than galley being that far off (spec section 5)."""


class AlignmentInvariantError(Exception):
    """The alignment broke its own rule: a token ended in no pairing or in
    two. A fault of the tool's code, not of a book, so it is not an
    EvaluationError and stops the command instead of being reported for
    one book and passed over."""


class GalleyFilesError(EvaluationError):
    """galley's files of a book do not fit together: a block with no page,
    a page that lines.json lacks, or a word of book.md in no known block."""


class GalleyRunError(EvaluationError):
    """`galley2epub run` on a book folder is not installed, failed, or did
    not finish in time."""


class EditSheetError(EvaluationError):
    """A sample of edits cannot be made or a sheet of verdicts cannot be
    read: a sheet that would be overwritten, a kind no edit has, a sheet
    that is not JSON or has a wrong field or verdict (spec section 9b)."""
