"""The book config: `book.toml`, written by the owner, read into a frozen BookConfig.

Every key of architecture section 6 is read, and an unknown key or a value
of the wrong type is a ConfigError that names the file and the key. A page
index past the end of the book is not checked here, since that needs the
PDF opened: analyze checks it.
"""

import math
import tomllib
import urllib.parse
from dataclasses import dataclass, replace
from enum import StrEnum
from pathlib import Path
from typing import assert_never

from galley.errors import ConfigError
from galley.model import Box


class Language(StrEnum):
    """The book's language, an ISO 639-1 code."""

    EN = "en"
    ES = "es"
    FR = "fr"
    DE = "de"
    IT = "it"


class OcrMode(StrEnum):
    """How far the book's own text layer is trusted (architecture section 7b)."""

    VERIFY = "verify"  # audited against Tesseract on a sample of pages
    TRUST = "trust"  # not audited; pages without a layer are still checked
    REDO = "redo"  # ignored: every page is read by Tesseract


@dataclass(frozen=True, slots=True)
class ExcludedRegion:
    """A part of one page left out of the book, such as a library stamp.
    `box` is in PDF points, origin at the top left of the page."""

    page_index: int
    box: Box


# The defaults of the correct stage's keys: the model the measurement of
# the plan notes-vision recommends, and LM Studio's own address
# (docs/specs/correct.md, section 3).
DEFAULT_CORRECT_MODEL = "qwen/qwen3.6-35b-a3b"
DEFAULT_CORRECT_SERVER = "http://localhost:1234"


@dataclass(frozen=True, slots=True, kw_only=True)
class BookConfig:
    """The config of one book. `pdf` is absolute; page indices count from 0.

    `plate_pages` are pages analyze makes plates whatever its rule finds;
    `contents_pages` are the pages of the printed table of contents, on
    which structure makes no heading; `front_matter_end` is the first page
    after the front matter, None when analyze is to find it, 0 to keep
    every page; `reread_footnotes` is whether layout re-reads each page's
    footnote band with Tesseract (architecture section 6). `correct_model`
    is the vision model the correct stage asks, as LM Studio names it,
    `correct_server` LM Studio's address on this machine, and
    `correct_second_model` the model of the second reading, None for none,
    and `correct_links` whether the stage also links notes to their
    references (docs/specs/correct.md, sections 3 and 9b).
    """

    pdf: Path
    title: str
    authors: tuple[str, ...]
    language: Language
    ocr: OcrMode = OcrMode.VERIFY
    correct: bool = False
    exclude_pages: tuple[int, ...] = ()
    exclude_regions: tuple[ExcludedRegion, ...] = ()
    cover_page: int | None = None
    plate_pages: tuple[int, ...] = ()
    contents_pages: tuple[int, ...] = ()
    front_matter_end: int | None = None
    reread_footnotes: bool = False
    correct_model: str = DEFAULT_CORRECT_MODEL
    correct_server: str = DEFAULT_CORRECT_SERVER
    correct_second_model: str | None = None
    correct_links: bool = True


# The hosts LM Studio may be asked on: this machine only, so that a book's
# text never leaves it (docs/specs/correct.md, section 3).
_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


_REQUIRED_KEYS = ("pdf", "title", "authors", "language")
_OPTIONAL_KEYS = (
    "ocr",
    "correct",
    "exclude_pages",
    "exclude_regions",
    "cover_page",
    "plate_pages",
    "contents_pages",
    "front_matter_end",
    "reread_footnotes",
    "correct_model",
    "correct_server",
    "correct_second_model",
    "correct_links",
)
_REGION_KEYS = ("page", "box")
_BOX_COORDINATES = 4


def read_config(path: Path) -> BookConfig:
    """The config in the `book.toml` at `path`.

    A relative `pdf` is taken against the folder of `path`; either is then
    resolved (made absolute, symbolic links followed). Raises ConfigError,
    naming the file and the key, when the file is missing or not TOML, a
    key is unknown or a required one missing, `title` or `authors` is
    empty, a value has the wrong type or is not one of its values, a page
    index is negative, a box is not four finite numbers with x0 < x1 and
    top < bottom, or the PDF is not a file.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as err:
        message = f"{path} does not exist; write the book's config there"
        raise ConfigError(message) from err
    except UnicodeDecodeError as err:
        message = f"{path} is not UTF-8 text: {err}"
        raise ConfigError(message) from err
    try:
        content = tomllib.loads(text)
    except tomllib.TOMLDecodeError as err:
        message = f"{path} is not valid TOML: {err}"
        raise ConfigError(message) from err
    config = _config_from_toml(content, path)
    pdf = config.pdf.resolve()
    if not pdf.is_file():
        message = f"{path}: key `pdf`: {pdf} does not exist or is not a file"
        raise ConfigError(message)
    return replace(config, pdf=pdf)


def _config_from_toml(content: dict[str, object], path: Path) -> BookConfig:
    """The config in the parsed TOML `content` of the file at `path`, whose
    folder a relative `pdf` is joined to, unresolved: this function does not
    touch the file system. `path` also names the file in a ConfigError."""
    _check_keys(content, _REQUIRED_KEYS, _OPTIONAL_KEYS, "", path)
    pdf = Path(_string(content["pdf"], "pdf", path))
    if not pdf.is_absolute():
        pdf = path.parent / pdf
    regions = _list(content.get("exclude_regions", []), "exclude_regions", path)
    cover_page = content.get("cover_page")
    front_matter_end = content.get("front_matter_end")
    return BookConfig(
        pdf=pdf,
        title=_not_empty(_string(content["title"], "title", path), "title", path),
        authors=_not_empty(
            tuple(
                _string(author, f"authors[{position}]", path)
                for position, author in enumerate(
                    _list(content["authors"], "authors", path)
                )
            ),
            "authors",
            path,
        ),
        language=_enum(Language, content["language"], "language", path),
        ocr=_enum(OcrMode, content.get("ocr", OcrMode.VERIFY.value), "ocr", path),
        correct=_bool(content.get("correct", False), "correct", path),
        exclude_pages=_page_indices(content, "exclude_pages", path),
        exclude_regions=tuple(
            _region(region, f"exclude_regions[{position}]", path)
            for position, region in enumerate(regions)
        ),
        cover_page=None
        if cover_page is None
        else _page_index(cover_page, "cover_page", path),
        plate_pages=_page_indices(content, "plate_pages", path),
        contents_pages=_page_indices(content, "contents_pages", path),
        front_matter_end=None
        if front_matter_end is None
        else _page_index(front_matter_end, "front_matter_end", path),
        reread_footnotes=_bool(
            content.get("reread_footnotes", False), "reread_footnotes", path
        ),
        correct_model=_not_empty(
            _string(
                content.get("correct_model", DEFAULT_CORRECT_MODEL),
                "correct_model",
                path,
            ),
            "correct_model",
            path,
        ),
        correct_server=_local_server(
            content.get("correct_server", DEFAULT_CORRECT_SERVER), path
        ),
        correct_second_model=None
        if (second := content.get("correct_second_model")) is None
        else _not_empty(
            _string(second, "correct_second_model", path),
            "correct_second_model",
            path,
        ),
        correct_links=_bool(content.get("correct_links", True), "correct_links", path),
    )


def _local_server(value: object, path: Path) -> str:
    """The value of `correct_server`: an `http` address on this machine,
    with a port or none, and no path, query or user; without a trailing
    slash."""
    key = "correct_server"
    address = _string(value, key, path).removesuffix("/")
    parts = urllib.parse.urlsplit(address)
    try:
        port = parts.port
    except ValueError as err:
        raise _error(path, key, f"{address!r} has no valid port") from err
    del port
    if (
        parts.scheme != "http"
        or parts.hostname not in _LOCAL_HOSTS
        or parts.username is not None
        or parts.path
        or parts.query
        or parts.fragment
    ):
        problem = (
            f"{address!r} is not an http address on this machine "
            "(localhost, 127.0.0.1 or [::1], with a port); the book's text "
            "is sent only to this machine"
        )
        raise _error(path, key, problem)
    return address


def _error(path: Path, key: str, problem: str) -> ConfigError:
    return ConfigError(f"{path}: key `{key}`: {problem}")


def _check_keys(
    table: dict[str, object],
    required: tuple[str, ...],
    optional: tuple[str, ...],
    prefix: str,
    path: Path,
) -> None:
    for key in required:
        if key not in table:
            raise _error(path, prefix + key, "missing; it is required")
    for key in table:
        if key not in required + optional:
            known = ", ".join(required + optional)
            raise _error(path, prefix + key, f"unknown; the keys are {known}")


def _string(value: object, key: str, path: Path) -> str:
    if not isinstance(value, str):
        raise _error(path, key, f"expected a string, found {value!r}")
    return value


def _not_empty[T: (str, tuple[str, ...])](value: T, key: str, path: Path) -> T:
    if len(value) == 0:
        raise _error(path, key, "must not be empty")
    return value


def _bool(value: object, key: str, path: Path) -> bool:
    if not isinstance(value, bool):
        raise _error(path, key, f"expected true or false, found {value!r}")
    return value


def _list(value: object, key: str, path: Path) -> tuple[object, ...]:
    if not isinstance(value, list):
        raise _error(path, key, f"expected a list, found {value!r}")
    return tuple(value)


def _enum[E: StrEnum](enum: type[E], value: object, key: str, path: Path) -> E:
    members = tuple(member.value for member in enum)
    if not isinstance(value, str) or value not in members:
        raise _error(
            path, key, f"expected one of {', '.join(members)}, found {value!r}"
        )
    return enum(value)


def _page_index(value: object, key: str, path: Path) -> int:
    # TOML true is a bool, which Python counts as an int; it is not a page.
    if isinstance(value, bool) or not isinstance(value, int):
        raise _error(path, key, f"expected a page index, found {value!r}")
    if value < 0:
        raise _error(path, key, f"a page index counts from 0, found {value}")
    return value


def _page_indices(content: dict[str, object], key: str, path: Path) -> tuple[int, ...]:
    """The list of page indices at `key` of `content`, in its order; none
    when the key is absent."""
    pages = _list(content.get(key, []), key, path)
    return tuple(
        _page_index(page, f"{key}[{position}]", path)
        for position, page in enumerate(pages)
    )


def _region(value: object, key: str, path: Path) -> ExcludedRegion:
    if not isinstance(value, dict):
        raise _error(path, key, f"expected a table {{page, box}}, found {value!r}")
    _check_keys(value, _REGION_KEYS, (), f"{key}.", path)
    return ExcludedRegion(
        page_index=_page_index(value["page"], f"{key}.page", path),
        box=_box(value["box"], f"{key}.box", path),
    )


def _box(value: object, key: str, path: Path) -> Box:
    # TOML true is a bool, which Python counts as an int; it is not a
    # number. TOML has nan and inf, which no page has.
    if (
        not isinstance(value, list)
        or len(value) != _BOX_COORDINATES
        or any(
            isinstance(coordinate, bool)
            or not isinstance(coordinate, int | float)
            or not math.isfinite(coordinate)
            for coordinate in value
        )
    ):
        raise _error(
            path,
            key,
            f"expected four finite numbers [x0, top, x1, bottom], found {value!r}",
        )
    x0, top, x1, bottom = (float(coordinate) for coordinate in value)
    # The owner draws these boxes by hand, so an empty one is a mistake. The
    # readers of model.py accept one, since their boxes come from the text
    # layer or OCR, and a stage decides what such a word is.
    if not x0 < x1:
        raise _error(path, key, f"x0 {x0} is not left of x1 {x1}")
    if not top < bottom:
        raise _error(path, key, f"top {top} is not above bottom {bottom}")
    return Box(x0, top, x1, bottom)


def book_toml_text(
    *, pdf: str, title: str, authors: tuple[str, ...], language: Language
) -> str:
    """The text of a `book.toml` with only the four required keys, which
    `read_config` reads back to these values: `pdf` as given, relative to
    the file's folder or absolute (architecture section 14)."""
    authors_list = ", ".join(_toml_string(author) for author in authors)
    return (
        f"pdf = {_toml_string(pdf)}\n"
        f"title = {_toml_string(title)}\n"
        f"authors = [{authors_list}]\n"
        f"language = {_toml_string(language.value)}\n"
    )


# The characters a TOML basic string must escape besides the control
# characters: the quote and the backslash (TOML 1.0, "String").
_TOML_ESCAPES = frozendict({'"': '\\"', "\\": "\\\\"})
# The last control character below the space, and DEL, which TOML also
# forbids unescaped.
_LAST_LOW_CONTROL = 0x1F
_DELETE = 0x7F


def _toml_string(text: str) -> str:
    """`text` as a TOML basic string, "..."; characters outside ASCII are
    written as they are, since the file is UTF-8."""
    escaped = "".join(
        _TOML_ESCAPES.get(character)
        or (
            f"\\u{ord(character):04X}"
            if ord(character) <= _LAST_LOW_CONTROL or ord(character) == _DELETE
            else character
        )
        for character in text
    )
    return f'"{escaped}"'


def tesseract_language(language: Language) -> str:
    """Tesseract's code of the language: en gives eng, es spa, fr fra, de deu, it ita."""
    match language:
        case Language.EN:
            return "eng"
        case Language.ES:
            return "spa"
        case Language.FR:
            return "fra"
        case Language.DE:
            return "deu"
        case Language.IT:
            return "ita"
        case _:
            assert_never(language)
