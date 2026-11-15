"""The committed excerpt PDFs are the integration fixtures of every stage."""

from pathlib import Path

import pdfplumber
import pytest

# The excerpts that scripts/fetch_samples.py cuts, with their page counts.
EXPECTED_EXCERPT_PAGES = {
    "kadesh_8-17": 10,
    "gierke_86-93_270-271": 10,
    "haskins_eval": 10,
    "stubbs_51_56-64": 10,
    "domesday_74-83": 10,
    "mariejol_210-219": 10,
}


def test_every_excerpt_is_committed(excerpt_pdf: frozendict[str, Path]) -> None:
    assert set(excerpt_pdf) == set(EXPECTED_EXCERPT_PAGES)


@pytest.mark.parametrize("name", sorted(EXPECTED_EXCERPT_PAGES))
def test_excerpt_has_its_pages_and_a_text_layer(
    excerpt_pdf: frozendict[str, Path], name: str
) -> None:
    with pdfplumber.open(excerpt_pdf[name]) as pdf:
        assert len(pdf.pages) == EXPECTED_EXCERPT_PAGES[name]
        assert pdf.pages[0].extract_words() != []
