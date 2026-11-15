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
