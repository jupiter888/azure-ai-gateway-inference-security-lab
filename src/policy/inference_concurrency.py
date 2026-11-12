"""
Process-local inference concurrency control.

Acquisition is nonblocking. A context manager releases capacity
after success or failure. This is not a distributed limit.
"""

from contextlib import contextmanager
from threading import BoundedSemaphore
from typing import Iterator


class InferenceBusy(Exception):
    pass


class InferenceConcurrency:
    def __init__(self, maximum: int = 2):
        if type(maximum) is not int or maximum < 1:
            raise ValueError("Concurrency maximum must be a positive integer")

        self._slots = BoundedSemaphore(maximum)

    @contextmanager
    def slot(self) -> Iterator[None]:
        if not self._slots.acquire(blocking=False):
            raise InferenceBusy("Inference capacity unavailable")

        try:
            yield
        finally:
            self._slots.release()