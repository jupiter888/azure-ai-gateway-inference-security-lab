"""
Concurrency tests without network requests or sleep-based timing.
"""

from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest

from src.policy.inference_concurrency import (
    InferenceBusy,
    InferenceConcurrency,
)


@pytest.mark.parametrize("maximum", [0, -1, True, 1.5])
def test_invalid_configuration_rejected(maximum):
    with pytest.raises(ValueError):
        InferenceConcurrency(maximum)


def test_available_slot_is_reusable():
    limiter = InferenceConcurrency(1)

    with limiter.slot():
        pass

    with limiter.slot():
        pass


def test_saturation_rejects_without_entering_body():
    limiter = InferenceConcurrency(2)
    entered = False

    with limiter.slot():
        with limiter.slot():
            with pytest.raises(InferenceBusy):
                with limiter.slot():
                    entered = True

    assert entered is False

    # Rejected acquisition must not leak or add capacity.
    with limiter.slot():
        with limiter.slot():
            with pytest.raises(InferenceBusy):
                with limiter.slot():
                    pass


def test_exception_releases_capacity():
    limiter = InferenceConcurrency(1)

    with pytest.raises(RuntimeError):
        with limiter.slot():
            raise RuntimeError("Synthetic backend failure")

    with limiter.slot():
        pass


def test_parallel_requests_rejected_while_slots_occupied():
    limiter = InferenceConcurrency(2)
    first_entered = Event()
    second_entered = Event()
    release = Event()

    def occupy(entered):
        with limiter.slot():
            entered.set()
            if not release.wait(timeout=10):
                raise RuntimeError("Test release signal missing")

    def attempt():
        try:
            with limiter.slot():
                return True
        except InferenceBusy:
            return False

    with ThreadPoolExecutor(max_workers=10) as executor:
        first = executor.submit(occupy, first_entered)
        second = executor.submit(occupy, second_entered)

        try:
            assert first_entered.wait(timeout=5)
            assert second_entered.wait(timeout=5)

            results = list(executor.map(lambda _: attempt(), range(20)))
            assert results == [False] * 20
        finally:
            release.set()

        first.result(timeout=5)
        second.result(timeout=5)

    with limiter.slot():
        with limiter.slot():
            pass