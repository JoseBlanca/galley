"""Tests of the exception classes of galley.errors (spec section 3)."""

import pytest

from galley.errors import (
    ConfigError,
    EditError,
    ExternalProgramError,
    FidelityError,
    GalleyError,
    InputFileError,
    PdfError,
)


@pytest.mark.parametrize(
    "error_class",
    [
        ConfigError,
        InputFileError,
        PdfError,
        ExternalProgramError,
        EditError,
        FidelityError,
    ],
)
def test_every_error_is_a_galley_error(error_class: type[Exception]) -> None:
    assert issubclass(error_class, GalleyError)


def test_fidelity_error_keeps_and_names_its_words() -> None:
    error = FidelityError(
        boundary="structure",
        missing=frozendict({"Greece,": 1}),
        invented=frozendict({"Greece,1": 2}),
        detail="page 4",
    )

    assert error.boundary == "structure"
    assert error.missing == frozendict({"Greece,": 1})
    assert error.invented == frozendict({"Greece,1": 2})
    assert error.detail == "page 4"
    message = str(error)
    assert "structure" in message
    assert "'Greece,' (1)" in message
    assert "'Greece,1' (2)" in message
    assert "page 4" in message
