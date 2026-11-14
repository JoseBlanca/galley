"""The thread pool that runs a function over the pages of a book.

`map_pages` runs a function on every item in a pool of threads and gives
the results in the order of the items, whatever the order they finish in,
so a stage's output is the same with 1 worker and with 8.
`map_pages_with_source` does the same for a function that needs a source
it may not share with another thread, a pdfplumber document: each worker
thread opens one, uses it for every item it takes, and closes it.
"""

import os
import threading
from collections.abc import Callable, Sequence
from concurrent.futures import FIRST_EXCEPTION, Future, ThreadPoolExecutor, wait
from contextlib import AbstractContextManager, nullcontext
from dataclasses import dataclass
from queue import SimpleQueue
from typing import Final

# Measured on 14 November 2026 (coding skill, "Threads and PDFium"):
# pdfplumber's extract_text on 200 pages of the Turney sample, one document
# per thread, on an M5 Pro with 6 performance cores, took 4.5 s with 1
# thread, 1.2 s with 6, and no less with more.
DEFAULT_WORKERS: Final[int] = min(6, os.process_cpu_count() or 1)


def map_pages[T, R](
    function: Callable[[T], R],
    items: Sequence[T],
    workers: int = DEFAULT_WORKERS,
) -> tuple[R, ...]:
    """`function` applied to every item in a pool of `workers` threads,
    the results in the order of `items`.

    When `function` raises, the exception of the first failing item in
    input order, among those that ran, is raised here; items not yet
    started may not run. `workers` below 1 is a ValueError.
    """
    return map_pages_with_source(
        lambda: nullcontext(None), lambda _, item: function(item), items, workers
    )


def map_pages_with_source[S, T, R](
    open_source: Callable[[], AbstractContextManager[S]],
    function: Callable[[S, T], R],
    items: Sequence[T],
    workers: int = DEFAULT_WORKERS,
) -> tuple[R, ...]:
    """`function(source, item)` for every item in a pool of `workers`
    threads, the results in the order of `items`.

    Each worker thread opens one source with `open_source()` once it has
    taken its first item, passes it with every item it takes, and closes it
    when no item is left or when `function` raises. A source is never
    shared between threads, and no more sources are opened than there are
    items.

    When `function` raises, the exception of the first failing item in
    input order, among those that ran, is raised here; items not yet
    started may not run. When `open_source` raises, that exception is
    raised here, and before any exception of `function`. Either way, every
    source that was opened is closed first. `workers` below 1 is a
    ValueError.
    """
    if workers < 1:
        message = f"workers must be at least 1, not {workers}"
        raise ValueError(message)
    queue: SimpleQueue[tuple[int, T] | None] = SimpleQueue()
    for entry in enumerate(items):
        queue.put(entry)
    for _ in range(workers):
        queue.put(None)  # one end mark for each worker
    stop = threading.Event()
    progress = tuple(_Progress() for _ in range(workers))

    def work(worker_progress: _Progress) -> tuple[tuple[int, R], ...]:
        return _work(open_source, function, queue, stop, worker_progress)

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = tuple(
            executor.submit(work, worker_progress) for worker_progress in progress
        )
        wait(futures, return_when=FIRST_EXCEPTION)
        # A failure stops the other workers before their next item.
        if any(future.exception() is not None for future in futures if future.done()):
            stop.set()
    # Every worker has ended here, and its source is closed.
    failure = _first_failure(futures, progress)
    if failure is not None:
        raise failure
    results = sorted(
        (entry for future in futures for entry in future.result()),
        key=lambda entry: entry[0],
    )
    assert len(results) == len(items), (len(results), len(items))
    return tuple(result for _, result in results)


@dataclass(slots=True)
class _Progress:
    """The item a worker is running, written by that worker alone and read by
    the calling thread only after the worker has ended, to tell which item
    failed. None until the worker's source is open."""

    item_index: int | None = None


def _work[S, T, R](
    open_source: Callable[[], AbstractContextManager[S]],
    function: Callable[[S, T], R],
    queue: SimpleQueue[tuple[int, T] | None],
    stop: threading.Event,
    progress: _Progress,
) -> tuple[tuple[int, R], ...]:
    entry = queue.get()
    if entry is None or stop.is_set():
        return ()
    results: list[tuple[int, R]] = []
    with open_source() as source:
        while entry is not None and not stop.is_set():
            item_index, item = entry
            progress.item_index = item_index
            results.append((item_index, function(source, item)))
            entry = queue.get()
    return tuple(results)


def _first_failure[R](
    futures: Sequence[Future[tuple[tuple[int, R], ...]]],
    progress: Sequence[_Progress],
) -> BaseException | None:
    # A worker whose progress has no item failed in open_source, before any
    # item, so its failure sorts first.
    failures = sorted(
        (
            (
                -1
                if worker_progress.item_index is None
                else worker_progress.item_index,
                error,
            )
            for future, worker_progress in zip(futures, progress, strict=True)
            if (error := future.exception()) is not None
        ),
        key=lambda failure: failure[0],
    )
    return failures[0][1] if failures else None
