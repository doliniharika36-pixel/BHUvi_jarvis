"""StreamingResponse implementations for LLM providers."""

from __future__ import annotations

from dataclasses import dataclass
from threading import Event, Lock
from typing import Callable, Iterator, Optional


# NOTE: We keep typing permissive here because mypy/pyright
# in this repo may not fully understand the cancellation-event type
# across modules.


from jarvis_os.core.ports.llm_provider import LLMCancelledError, StreamingResponse


class _ThreadSafeTokenIterator:
    def __init__(self, factory: Callable[[Event], Iterator[str]]) -> None:
        self._cancel_event: Event = Event()
        self._factory = factory
        self._iter: Optional[Iterator[str]] = None
        self._lock = Lock()

    def __iter__(self) -> "_ThreadSafeTokenIterator":
        return self

    def __next__(self) -> str:
        if self._cancel_event.is_set():
            raise LLMCancelledError("Stream cancelled by caller.")

        with self._lock:
            if self._iter is None:
                self._iter = self._factory(self._cancel_event)

            if self._iter is None:
                raise StopIteration

            # If cancelled after iterator creation but before next(), raise cleanly.
            if self._cancel_event.is_set():
                raise LLMCancelledError("Stream cancelled by caller.")

            return next(self._iter)


@dataclass
class SyncStreamingResponse(StreamingResponse):
    """Synchronous streaming response.

    Wraps a token iterator factory so we can create/stop on demand.
    """

    _iterator: _ThreadSafeTokenIterator
    _complete: bool = False

    def __init__(self, iterator_factory: Callable[[Event], Iterator[str]]) -> None:
        self._iterator = _ThreadSafeTokenIterator(iterator_factory)
        self._complete = False


    def __iter__(self) -> Iterator[str]:
        try:
            for token in self._iterator:
                yield token
            self._complete = True
        except LLMCancelledError:
            # Cancellation is considered not complete.
            self._complete = False
            raise

    def cancel(self) -> None:
        # Signal cancel by toggling underlying event via iter object.
        self._iterator._cancel_event.set()  # noqa: SLF001

    def is_complete(self) -> bool:
        return self._complete

