"""Tests of galley.config: reading book.toml (spec section 3, architecture section 6)."""

import json
import re
from pathlib import Path

import pytest

from galley.config import (
    BookConfig,
    ExcludedRegion,
    Language,
    OcrMode,
    read_config,
    tesseract_language,
)
from galley.errors import ConfigError
from galley.model import Box

KADESH = "kadesh_8-17"


def _toml_string(text: str) -> str:
    # A JSON string of ordinary characters is a TOML basic string.
    return json.dumps(text)


def _required_keys(pdf: Path) -> dict[str, str]:
    """The required keys of a config, as TOML values."""
    return {
        "pdf": _toml_string(str(pdf)),
        "title": '"The Battle of Kadesh"',
        "authors": '["James Henry Breasted"]',
        "language": '"en"',
    }


def _write_config(folder: Path, keys: dict[str, str]) -> Path:
    path = folder / "book.toml"
    path.write_text(
        "".join(f"{key} = {value}\n" for key, value in keys.items()), encoding="utf-8"
    )
    return path


def test_config_with_every_key_is_read_into_its_values(
    tmp_path: Path, excerpt_pdf: dict[str, Path]
) -> None:
    pdf = excerpt_pdf[KADESH]
    path = _write_config(
        tmp_path,
        {
            "pdf": _toml_string(str(pdf)),
            "title": '"Die Schlacht bei Kadesch"',
            "authors": '["James Henry Breasted", "A. N. Other"]',
            "language": '"de"',
            "ocr": '"redo"',
            "correct": "true",
            "exclude_pages": "[9, 8]",
            "exclude_regions": "[{page = 0, box = [240, 620, 252, 632.5]}, {page = 3, box = [1.5, 2, 3, 4]}]",
            "cover_page": "1",
        },
    )

    assert read_config(path) == BookConfig(
        pdf=pdf,
        title="Die Schlacht bei Kadesch",
        authors=("James Henry Breasted", "A. N. Other"),
        language=Language.DE,
        ocr=OcrMode.REDO,
        correct=True,
        exclude_pages=(9, 8),
        exclude_regions=(
            ExcludedRegion(page_index=0, box=Box(240.0, 620.0, 252.0, 632.5)),
            ExcludedRegion(page_index=3, box=Box(1.5, 2.0, 3.0, 4.0)),
        ),
        cover_page=1,
    )


def test_config_with_only_the_required_keys_has_the_defaults(
    tmp_path: Path, excerpt_pdf: dict[str, Path]
) -> None:
    pdf = excerpt_pdf[KADESH]
    path = _write_config(tmp_path, _required_keys(pdf))

    assert read_config(path) == BookConfig(
        pdf=pdf,
        title="The Battle of Kadesh",
        authors=("James Henry Breasted",),
        language=Language.EN,
        ocr=OcrMode.VERIFY,
        correct=False,
        exclude_pages=(),
        exclude_regions=(),
        cover_page=None,
    )


def test_relative_pdf_is_resolved_against_the_folder_of_the_config(
    tmp_path: Path,
) -> None:
    (tmp_path / "scans").mkdir()
    (tmp_path / "scans" / "book.pdf").write_bytes(b"%PDF-1.4")
    (tmp_path / "config").mkdir()
    keys = _required_keys(tmp_path) | {"pdf": '"../scans/book.pdf"'}
    path = _write_config(tmp_path / "config", keys)

    config = read_config(path)

    assert config.pdf == (tmp_path / "scans" / "book.pdf").resolve()
    assert ".." not in config.pdf.parts
    assert config.pdf.is_absolute()


def test_absolute_pdf_is_resolved(tmp_path: Path) -> None:
    (tmp_path / "scans").mkdir()
    (tmp_path / "scans" / "book.pdf").write_bytes(b"%PDF-1.4")
    (tmp_path / "link.pdf").symlink_to(tmp_path / "scans" / "book.pdf")
    path = _write_config(tmp_path, _required_keys(tmp_path / "link.pdf"))

    assert read_config(path).pdf == (tmp_path / "scans" / "book.pdf").resolve()


@pytest.mark.parametrize(("key", "value"), [("title", '""'), ("authors", "[]")])
def test_empty_title_or_authors_is_an_error(
    tmp_path: Path, excerpt_pdf: dict[str, Path], key: str, value: str
) -> None:
    path = _write_config(tmp_path, _required_keys(excerpt_pdf[KADESH]) | {key: value})
    _assert_config_error(path, key)
    with pytest.raises(ConfigError, match="must not be empty"):
        read_config(path)


def test_pdf_that_is_a_directory_is_an_error(tmp_path: Path) -> None:
    (tmp_path / "scans.pdf").mkdir()
    path = _write_config(tmp_path, _required_keys(tmp_path / "scans.pdf"))
    _assert_config_error(path, "pdf")


def _assert_config_error(path: Path, key: str) -> None:
    with pytest.raises(ConfigError, match=re.escape(str(path))) as caught:
        read_config(path)
    assert f"`{key}`" in str(caught.value)


def test_missing_config_file_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match=re.escape(str(tmp_path / "book.toml"))):
        read_config(tmp_path / "book.toml")


def test_config_that_is_not_toml_is_an_error(tmp_path: Path) -> None:
    path = tmp_path / "book.toml"
    path.write_text('title = "The Battle\n', encoding="utf-8")
    with pytest.raises(ConfigError, match=re.escape(str(path))) as caught:
        read_config(path)
    assert "line 1" in str(caught.value)


def test_unknown_key_is_an_error(tmp_path: Path, excerpt_pdf: dict[str, Path]) -> None:
    path = _write_config(
        tmp_path, _required_keys(excerpt_pdf[KADESH]) | {"subtitle": '"x"'}
    )
    _assert_config_error(path, "subtitle")


def test_unknown_key_inside_a_region_is_an_error(
    tmp_path: Path, excerpt_pdf: dict[str, Path]
) -> None:
    keys = _required_keys(excerpt_pdf[KADESH]) | {
        "exclude_regions": '[{page = 0, box = [1, 2, 3, 4], colour = "red"}]'
    }
    path = _write_config(tmp_path, keys)
    _assert_config_error(path, "exclude_regions[0].colour")


@pytest.mark.parametrize("key", ["pdf", "title", "authors", "language"])
def test_missing_required_key_is_an_error(
    tmp_path: Path, excerpt_pdf: dict[str, Path], key: str
) -> None:
    keys = {
        name: value
        for name, value in _required_keys(excerpt_pdf[KADESH]).items()
        if name != key
    }
    path = _write_config(tmp_path, keys)
    _assert_config_error(path, key)


def test_region_without_its_box_is_an_error(
    tmp_path: Path, excerpt_pdf: dict[str, Path]
) -> None:
    keys = _required_keys(excerpt_pdf[KADESH]) | {"exclude_regions": "[{page = 0}]"}
    path = _write_config(tmp_path, keys)
    _assert_config_error(path, "exclude_regions[0].box")


@pytest.mark.parametrize(
    ("key", "value", "named_key"),
    [
        ("authors", '"Breasted"', "authors"),
        ("authors", '["Breasted", 2]', "authors[1]"),
        ("title", "5", "title"),
        ("pdf", "5", "pdf"),
        ("correct", '"yes"', "correct"),
        ("exclude_pages", "[1.5]", "exclude_pages[0]"),
        ("exclude_pages", "3", "exclude_pages"),
        ("cover_page", "true", "cover_page"),
        ("exclude_regions", '"x"', "exclude_regions"),
        ("exclude_regions", "[3]", "exclude_regions[0]"),
        (
            "exclude_regions",
            '[{page = "0", box = [1, 2, 3, 4]}]',
            "exclude_regions[0].page",
        ),
    ],
)
def test_value_of_the_wrong_type_is_an_error(
    tmp_path: Path, excerpt_pdf: dict[str, Path], key: str, value: str, named_key: str
) -> None:
    path = _write_config(tmp_path, _required_keys(excerpt_pdf[KADESH]) | {key: value})
    _assert_config_error(path, named_key)


def test_language_that_is_not_one_of_its_values_is_an_error(
    tmp_path: Path, excerpt_pdf: dict[str, Path]
) -> None:
    path = _write_config(
        tmp_path, _required_keys(excerpt_pdf[KADESH]) | {"language": '"english"'}
    )
    _assert_config_error(path, "language")


def test_ocr_that_is_not_one_of_its_values_is_an_error(
    tmp_path: Path, excerpt_pdf: dict[str, Path]
) -> None:
    path = _write_config(
        tmp_path, _required_keys(excerpt_pdf[KADESH]) | {"ocr": '"always"'}
    )
    _assert_config_error(path, "ocr")


@pytest.mark.parametrize(
    ("key", "value", "named_key"),
    [
        ("exclude_pages", "[3, -1]", "exclude_pages[1]"),
        ("cover_page", "-1", "cover_page"),
        (
            "exclude_regions",
            "[{page = -2, box = [1, 2, 3, 4]}]",
            "exclude_regions[0].page",
        ),
    ],
)
def test_negative_page_index_is_an_error(
    tmp_path: Path, excerpt_pdf: dict[str, Path], key: str, value: str, named_key: str
) -> None:
    path = _write_config(tmp_path, _required_keys(excerpt_pdf[KADESH]) | {key: value})
    _assert_config_error(path, named_key)


@pytest.mark.parametrize(
    "box",
    ["[1, 2, 3]", "[1, 2, 3, 4, 5]", '[1, 2, "3", 4]', "[true, 2, 3, 4]", '"1 2 3 4"'],
)
def test_box_that_is_not_four_numbers_is_an_error(
    tmp_path: Path, excerpt_pdf: dict[str, Path], box: str
) -> None:
    keys = _required_keys(excerpt_pdf[KADESH]) | {
        "exclude_regions": f"[{{page = 0, box = {box}}}]"
    }
    path = _write_config(tmp_path, keys)
    _assert_config_error(path, "exclude_regions[0].box")


@pytest.mark.parametrize("box", ["[3, 2, 3, 4]", "[5, 2, 3, 4]"])
def test_box_whose_x0_is_not_left_of_x1_is_an_error(
    tmp_path: Path, excerpt_pdf: dict[str, Path], box: str
) -> None:
    keys = _required_keys(excerpt_pdf[KADESH]) | {
        "exclude_regions": f"[{{page = 0, box = {box}}}]"
    }
    path = _write_config(tmp_path, keys)
    _assert_config_error(path, "exclude_regions[0].box")


@pytest.mark.parametrize("box", ["[1, 4, 3, 4]", "[1, 5, 3, 4]"])
def test_box_whose_top_is_not_above_bottom_is_an_error(
    tmp_path: Path, excerpt_pdf: dict[str, Path], box: str
) -> None:
    keys = _required_keys(excerpt_pdf[KADESH]) | {
        "exclude_regions": f"[{{page = 0, box = {box}}}]"
    }
    path = _write_config(tmp_path, keys)
    _assert_config_error(path, "exclude_regions[0].box")


def test_pdf_that_does_not_exist_is_an_error(tmp_path: Path) -> None:
    path = _write_config(tmp_path, _required_keys(tmp_path / "missing.pdf"))
    with pytest.raises(ConfigError, match=re.escape(str(path))) as caught:
        read_config(path)
    assert "missing.pdf" in str(caught.value)
    assert "`pdf`" in str(caught.value)


@pytest.mark.parametrize(
    ("language", "code"),
    [
        (Language.EN, "eng"),
        (Language.ES, "spa"),
        (Language.FR, "fra"),
        (Language.DE, "deu"),
        (Language.IT, "ita"),
    ],
)
def test_tesseract_language_is_the_three_letter_code(
    language: Language, code: str
) -> None:
    assert tesseract_language(language) == code


@pytest.mark.parametrize(
    "box", ["[nan, 2, 3, 4]", "[1, 2, inf, 4]", "[1, -inf, 3, 4]", "[1, 2, 3, nan]"]
)
def test_box_with_a_number_that_is_not_finite_is_an_error(
    tmp_path: Path, excerpt_pdf: dict[str, Path], box: str
) -> None:
    keys = _required_keys(excerpt_pdf[KADESH]) | {
        "exclude_regions": f"[{{page = 0, box = {box}}}]"
    }
    path = _write_config(tmp_path, keys)
    _assert_config_error(path, "exclude_regions[0].box")
