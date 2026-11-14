"""Tests of galley.parallel (spec section 4)."""

import os
import threading
import time
from collections.abc import Callable, Generator
from contextlib import AbstractContextManager, contextmanager, suppress
from dataclasses import dataclass, field

import pytest

from galley.parallel import DEFAULT_WORKERS, map_pages, map_pages_with_source

ITEMS = tuple(range(20))
SQUARES = tuple(item * item for item in ITEMS)
SLEEP_UNIT_S = 0.002


def square(item: int) -> int:
    return item * item


@dataclass(slots=True)
class CountingSource:
    """A source factory that records, under a lock, every source it opens
    and closes. Mutable, as a recorder must be; it lives in one test."""

    lock: threading.Lock = field(default_factory=threading.Lock)
    opened: list[int] = field(default_factory=list)
    closed: list[int] = field(default_factory=list)
    fail_on_opening: int | None = None

    def open(self) -> AbstractContextManager[int]:
        return self._source()

    def is_open(self, source: int) -> bool:
        with self.lock:
            return source in self.opened and source not in self.closed

    @contextmanager
    def _source(self) -> Generator[int]:
        with self.lock:
            source = len(self.opened)
            if source == self.fail_on_opening:
                message = f"source {source} cannot be opened"
                raise OSError(message)
            self.opened.append(source)
        try:
            yield source
        finally:
            with self.lock:
                self.closed.append(source)


@dataclass(slots=True)
class SpreadSquare:
    """`square` that sleeps a little, so that one worker cannot take every
    item before the others start, and records the threads it ran in.
    Mutable, as a recorder must be; it lives in one test."""

    lock: threading.Lock = field(default_factory=threading.Lock)
    threads: set[int] = field(default_factory=set)

    def __call__(self, item: int) -> int:
        with self.lock:
            self.threads.add(threading.get_ident())
        time.sleep(SLEEP_UNIT_S)
        return item * item


def test_default_workers_is_at_most_6_and_at_least_1() -> None:
    assert DEFAULT_WORKERS == min(6, os.process_cpu_count() or 1)


@pytest.mark.parametrize("workers", [1, 3, 8])
def test_map_pages_gives_the_results_in_input_order(workers: int) -> None:
    spread_square = SpreadSquare()

    assert map_pages(spread_square, ITEMS, workers) == SQUARES
    assert (len(spread_square.threads) > 1) == (workers > 1)


def test_map_pages_keeps_input_order_when_later_items_finish_first() -> None:
    def sleep_less_for_later_items(item: int) -> int:
        time.sleep((len(ITEMS) - item) * SLEEP_UNIT_S)
        return item

    assert map_pages(sleep_less_for_later_items, ITEMS, 4) == ITEMS


def test_map_pages_gives_the_same_tuple_with_1_3_and_8_workers() -> None:
    spread_squares = {workers: SpreadSquare() for workers in (1, 3, 8)}
    results = {
        workers: map_pages(spread_square, ITEMS, workers)
        for workers, spread_square in spread_squares.items()
    }

    assert results == {1: SQUARES, 3: SQUARES, 8: SQUARES}
    assert len(spread_squares[1].threads) == 1
    assert len(spread_squares[3].threads) > 1
    assert len(spread_squares[8].threads) > 1


def test_map_pages_of_no_items_is_empty() -> None:
    assert map_pages(square, (), 3) == ()


def test_map_pages_raises_the_exception_of_the_failing_item() -> None:
    def fail_on_5(item: int) -> int:
        if item == 5:
            message = "item 5 failed"
            raise ValueError(message)
        return item

    with pytest.raises(ValueError, match="item 5 failed"):
        map_pages(fail_on_5, ITEMS, 3)


@pytest.mark.parametrize(
    "call",
    [
        pytest.param(lambda workers: map_pages(square, ITEMS, workers), id="map_pages"),
        pytest.param(
            lambda workers: map_pages_with_source(
                CountingSource().open, lambda _, item: item, ITEMS, workers
            ),
            id="map_pages_with_source",
        ),
    ],
)
@pytest.mark.parametrize("workers", [0, -1])
def test_workers_below_1_raises_value_error(
    call: Callable[[int], tuple[int, ...]], workers: int
) -> None:
    with pytest.raises(ValueError, match=f"workers must be at least 1, not {workers}"):
        call(workers)


@pytest.mark.parametrize("workers", [1, 3, 8])
def test_map_pages_with_source_gives_the_results_in_input_order(workers: int) -> None:
    sources = CountingSource()
    spread_square = SpreadSquare()

    def square_with_open_source(source: int, item: int) -> int:
        assert sources.is_open(source)
        return spread_square(item)

    assert (
        map_pages_with_source(sources.open, square_with_open_source, ITEMS, workers)
        == SQUARES
    )
    assert (len(spread_square.threads) > 1) == (workers > 1)


def test_map_pages_with_source_keeps_input_order_when_later_items_finish_first() -> (
    None
):
    def sleep_less_for_later_items(_: int, item: int) -> int:
        time.sleep((len(ITEMS) - item) * SLEEP_UNIT_S)
        return item

    results = map_pages_with_source(
        CountingSource().open, sleep_less_for_later_items, ITEMS, 4
    )

    assert results == ITEMS


def test_3_workers_on_20_items_open_at_most_3_sources_and_close_each() -> None:
    sources = CountingSource()

    def slow_identity(_: int, item: int) -> int:
        time.sleep(SLEEP_UNIT_S)
        return item

    map_pages_with_source(sources.open, slow_identity, ITEMS, 3)

    assert 1 <= len(sources.opened) <= 3
    assert sorted(sources.closed) == sorted(sources.opened)


def test_8_workers_on_2_items_open_at_most_2_sources() -> None:
    sources = CountingSource()

    results = map_pages_with_source(sources.open, lambda _, item: item, (0, 1), 8)

    assert results == (0, 1)
    assert 1 <= len(sources.opened) <= 2
    assert sorted(sources.closed) == sorted(sources.opened)


def test_map_pages_with_source_of_no_items_opens_no_source() -> None:
    sources = CountingSource()

    assert map_pages_with_source(sources.open, lambda _, item: item, (), 3) == ()
    assert sources.opened == []


def test_exception_for_item_5_reaches_the_caller_and_every_source_is_closed() -> None:
    sources = CountingSource()

    def fail_on_5(_: int, item: int) -> int:
        time.sleep(SLEEP_UNIT_S)
        if item == 5:
            message = "item 5 failed"
            raise ValueError(message)
        return item

    with pytest.raises(ValueError, match="item 5 failed"):
        map_pages_with_source(sources.open, fail_on_5, ITEMS, 3)

    assert sources.opened != []
    assert sorted(sources.closed) == sorted(sources.opened)


def test_the_first_failing_item_in_input_order_is_the_one_raised() -> None:
    every_item_started = threading.Barrier(10)

    def fail_on_3_late_and_on_7_early(_: int, item: int) -> int:
        every_item_started.wait(timeout=5)
        if item == 3:
            time.sleep(20 * SLEEP_UNIT_S)
            message = "item 3 failed"
            raise ValueError(message)
        if item == 7:
            message = "item 7 failed"
            raise ValueError(message)
        return item

    # 10 workers on 10 items, and the barrier: every item has started before
    # item 7 fails, and item 3 fails after it.
    with pytest.raises(ValueError, match="item 3 failed"):
        map_pages_with_source(
            CountingSource().open, fail_on_3_late_and_on_7_early, tuple(range(10)), 10
        )


def test_open_source_that_raises_reaches_the_caller_and_other_sources_close() -> None:
    sources = CountingSource(fail_on_opening=1)

    def slow_identity(_: int, item: int) -> int:
        # Slow enough that a second worker takes an item, and tries to open
        # the source that fails, before the first worker is done.
        time.sleep(SLEEP_UNIT_S)
        return item

    with pytest.raises(OSError, match="source 1 cannot be opened"):
        map_pages_with_source(sources.open, slow_identity, ITEMS, 3)

    assert sources.opened != []
    assert sorted(sources.closed) == sorted(sources.opened)


@contextmanager
def swallowing_source() -> Generator[None]:
    """A source whose closing swallows the exception of `function`, as a
    defective source could: the worker then ends as if it had no item left."""
    with suppress(ValueError):
        yield


def test_items_lost_to_a_source_that_swallows_an_error_raise_runtime_error() -> None:
    def fail_on_3(_: None, item: int) -> int:
        if item == 3:
            message = "item 3 failed"
            raise ValueError(message)
        return item

    with pytest.raises(RuntimeError, match=r"item indices \[3, 4, 5\] are missing"):
        map_pages_with_source(swallowing_source, fail_on_3, tuple(range(6)), 1)


def test_open_source_error_wins_over_a_function_error_in_another_worker() -> None:
    both_failing = threading.Barrier(2)
    opened = CountingSource()

    @contextmanager
    def second_opening_fails() -> Generator[int]:
        with opened.lock:
            opening = len(opened.opened)
            opened.opened.append(opening)
        if opening == 1:
            both_failing.wait(timeout=5)
            message = "the second source cannot be opened"
            raise OSError(message)
        yield opening

    def fail_on_0(_: int, item: int) -> int:
        if item == 0:
            # Fail only once the other worker is inside open_source, so
            # that both fail whichever raises first.
            both_failing.wait(timeout=5)
            message = "item 0 failed"
            raise ValueError(message)
        return item

    with pytest.raises(OSError, match="the second source cannot be opened"):
        map_pages_with_source(second_opening_fails, fail_on_0, ITEMS, 2)
