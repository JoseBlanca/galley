"""The model's answers kept in the book folder (docs/specs/correct.md,
section 4b): a request whose answer is kept with the same request's
SHA-256 is not sent again."""

import hashlib
import threading
from collections.abc import Callable
from enum import StrEnum
from pathlib import Path

from galley.correct._lmstudio import Reading, read_image, request_data
from galley.model import AnswerKind, KeptAnswer, read_kept_answer, write_kept_answer


class AnswerSource(StrEnum):
    """Where an answer came from: the book folder or the model."""

    KEPT = "kept"
    ASKED = "asked"


def answer_path(answers_dir: Path, kind: AnswerKind, page_index: int) -> Path:
    """The file of the answer of `kind` for the page `page_index`:
    `<kind>-<page index, 4 digits>.json` in `answers_dir`."""
    return answers_dir / f"{kind}-{page_index:04d}.json"


def once(check: Callable[[], None]) -> Callable[[], None]:
    """A function that calls `check` the first time it is called and, once
    `check` has returned, never again; safe to call from several threads,
    which wait while `check` runs. When `check` raises, the next call
    calls it again."""
    lock = threading.Lock()
    passed: list[bool] = []  # written only under the lock

    def check_once() -> None:
        with lock:
            if not passed:
                check()
                passed.append(True)

    return check_once


def kept_or_read(
    answers_dir: Path,
    kind: AnswerKind,
    page_index: int,
    server: str,
    model: str,
    png: bytes,
    what: str,
    prompt: str,
    before_asking: Callable[[], None],
) -> tuple[Reading, AnswerSource]:
    """`model`'s reading of the PNG image `png` with `prompt`: the kept
    answer of `kind` for the page when it was given to the same request,
    otherwise read through LM Studio at `server` and kept, in place of the
    answer there, after calling `before_asking`, which checks the server
    (section 4) and raises when it fails. An answer cut short is kept as such; a failed request
    raises as read_image does and keeps nothing. Raises InputFileError for
    a kept answer that cannot be read. Must not run in two threads for one
    page and kind at once."""
    path = answer_path(answers_dir, kind, page_index)
    request_sha256 = hashlib.sha256(request_data(model, png, prompt)).hexdigest()
    kept = read_kept_answer(path)
    if kept is not None and kept.request_sha256 == request_sha256:
        return Reading(kept.text, cut_short=kept.cut_short), AnswerSource.KEPT
    before_asking()
    reading = read_image(server, model, png, what, prompt)
    write_kept_answer(
        path,
        KeptAnswer(
            page_index=page_index,
            kind=kind,
            model=model,
            prompt=prompt,
            image_sha256=hashlib.sha256(png).hexdigest(),
            request_sha256=request_sha256,
            text=reading.text,
            cut_short=reading.cut_short,
        ),
    )
    return reading, AnswerSource.ASKED
