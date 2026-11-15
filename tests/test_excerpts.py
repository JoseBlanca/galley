"""The committed excerpt PDFs are the integration fixtures of every stage."""

from pathlib import Path

import pytest

from galley.text_layer import open_pdf

# The excerpts that scripts/fetch_samples.py cuts, with their page counts.
EXPECTED_EXCERPT_PAGES = {
    "kadesh_8-17": 10,
    "gierke_86-93_270-271": 10,
    "haskins_eval": 10,
    "stubbs_51_56-64": 10,
    "domesday_74-83": 10,
    "mariejol_210-219": 10,
}

# The pages of each excerpt, by index in the excerpt, that have no word in
# their text layer, as scripts/fetch_samples.py describes them: Kadesh's
# blank page and Haskins' blank page before the index. Every other page
# has words.
PAGES_WITHOUT_WORDS = {
    "kadesh_8-17": (9,),
    "gierke_86-93_270-271": (),
    "haskins_eval": (8,),
    "stubbs_51_56-64": (),
    "domesday_74-83": (),
    "mariejol_210-219": (),
}


def test_every_excerpt_is_committed(excerpt_pdf: frozendict[str, Path]) -> None:
    assert set(excerpt_pdf) == set(EXPECTED_EXCERPT_PAGES)


@pytest.mark.parametrize("name", sorted(EXPECTED_EXCERPT_PAGES))
def test_excerpt_has_its_pages_and_words_on_each_but_its_blank_pages(
    excerpt_pdf: frozendict[str, Path], name: str
) -> None:
    with open_pdf(excerpt_pdf[name]) as pdf:
        assert len(pdf.pages) == EXPECTED_EXCERPT_PAGES[name]
        pages_without_words = tuple(
            page_index
            for page_index, page in enumerate(pdf.pages)
            if not page.extract_words()
        )

    assert pages_without_words == PAGES_WITHOUT_WORDS[name]
