"""The calls to LM Studio's server on this machine (docs/specs/correct.md,
section 4): the list of its models, and a page's image read by a model."""

import base64
import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from email.message import Message
from typing import IO, Final, override

from galley.errors import ExternalProgramError

# Section 4: the prompt the measurement of the plan notes-vision used.
PROMPT: Final[str] = (
    "Transcribe the printed text in this image exactly as it is printed, "
    "line by line, in reading order. Do not correct spelling or wording, "
    "do not add anything, no commentary, no formatting. "
    "Skip hieroglyphs and drawings."
)
# Section 4: a page of about 600 words took 1,409 tokens (Kadesh page 11);
# an answer this long is a model repeating itself.
MAX_TOKENS: Final[int] = 6000
# Section 4: the list of models answers at once when the server runs.
_LIST_TIMEOUT_S: Final[float] = 10
# Section 4, guessed: a page took 12.8 s on average with the 35B model, and
# the first request also waits for LM Studio to load the model.
_PAGE_TIMEOUT_S: Final[float] = 600
# How much of an unexpected answer an error message quotes.
_QUOTED: Final[int] = 200


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Refuses every redirect: a request goes to LM Studio's address only."""

    @override
    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: IO[bytes],
        code: int,
        msg: str,
        headers: Message,
        newurl: str,
    ) -> urllib.request.Request | None:
        message = (
            f"LM Studio's address {req.full_url} answered with a redirect to {newurl}"
        )
        raise ExternalProgramError(message)


# Section 4: no proxy, though the environment names one (urllib's default
# opener follows http_proxy), and no redirect, so that a book's text goes
# to this machine only.
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect)


@dataclass(frozen=True, slots=True)
class Reading:
    """A model's answer for one image: its text, and whether it was cut
    short at MAX_TOKENS."""

    text: str
    cut_short: bool


def _not_running(server: str) -> ExternalProgramError:
    return ExternalProgramError(
        f"LM Studio's server is not running at {server}: start it in LM Studio "
        "or with `lms server start`"
    )


def _quoted(data: bytes) -> str:
    return data[:_QUOTED].decode("utf-8", errors="replace")


def list_models(server: str) -> tuple[str, ...]:
    """The ids of the models LM Studio lists at `server`. Raises
    ExternalProgramError when nothing answers there or the answer is not a
    list of models."""
    url = f"{server}/v1/models"
    try:
        with _OPENER.open(url, timeout=_LIST_TIMEOUT_S) as response:
            data = response.read()
    except (urllib.error.URLError, TimeoutError, ConnectionError) as err:
        raise _not_running(server) from err
    try:
        listed = json.loads(data)
        return tuple(str(model["id"]) for model in listed["data"])
    except (ValueError, KeyError, TypeError) as err:
        message = f"{url} did not answer with a list of models: {_quoted(data)}"
        raise ExternalProgramError(message) from err


def check_models(server: str, models: tuple[str, ...]) -> None:
    """ExternalProgramError when LM Studio at `server` does not answer, or
    lacks one of `models`, with how to get it and the models it has."""
    listed = list_models(server)
    for model in models:
        if model not in listed:
            message = (
                f"LM Studio has no model {model}: download it with `lms get {model}`; "
                f"it has {', '.join(listed) or 'none'}"
            )
            raise ExternalProgramError(message)


def request_body(model: str, png: bytes) -> dict[str, object]:
    """The JSON body of the request that asks `model` to read the image."""
    image = base64.b64encode(png).decode("ascii")
    return {
        "model": model,
        "temperature": 0,
        "max_tokens": MAX_TOKENS,
        "reasoning_effort": "none",
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": PROMPT},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{image}"},
                    },
                ],
            }
        ],
    }


def read_image(server: str, model: str, png: bytes, what: str) -> Reading:
    """`model`'s reading of the PNG image `png`, through LM Studio at
    `server`. `what` names the image in an error ("page 11"). Raises
    ExternalProgramError on a refused connection, a timeout, an HTTP error
    status or an answer without its text."""
    url = f"{server}/v1/chat/completions"
    request = urllib.request.Request(
        url,
        data=json.dumps(request_body(model, png)).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with _OPENER.open(request, timeout=_PAGE_TIMEOUT_S) as response:
            data = response.read()
    except urllib.error.HTTPError as err:
        with err:
            said = _quoted(err.read())
        message = (
            f"LM Studio at {server} refused to read {what} with {model}: "
            f"HTTP {err.code}, {said}"
        )
        raise ExternalProgramError(message) from err
    except (urllib.error.URLError, ConnectionError) as err:
        raise _not_running(server) from err
    except TimeoutError as err:
        message = (
            f"LM Studio at {server} did not answer for {what} within "
            f"{_PAGE_TIMEOUT_S:.0f} s"
        )
        raise ExternalProgramError(message) from err
    try:
        answer = json.loads(data)
        choice = answer["choices"][0]
        text = choice["message"]["content"]
        finish = choice.get("finish_reason")
    except (ValueError, KeyError, IndexError, TypeError) as err:
        message = f"LM Studio at {server} gave no text for {what}: {_quoted(data)}"
        raise ExternalProgramError(message) from err
    if not isinstance(text, str):
        message = f"LM Studio at {server} gave no text for {what}: {_quoted(data)}"
        raise ExternalProgramError(message)
    return Reading(text, cut_short=finish == "length")
