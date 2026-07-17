from __future__ import annotations

import sys
import threading
import time
from collections.abc import Callable
from typing import TextIO

ProgressCallback = Callable[[str, str | None], None]


def emit_progress(
    progress: ProgressCallback | None,
    phase: str,
    detail: str | None = None,
) -> None:
    if progress is not None:
        progress(phase, detail)


class ProgressReporter:
    """Emit human-readable progress on stderr without contaminating JSON stdout."""

    def __init__(
        self,
        command: str,
        *,
        stream: TextIO | None = None,
        interval_seconds: float = 15.0,
    ) -> None:
        self.command = command
        self.stream = sys.stderr if stream is None else stream
        self.interval_seconds = interval_seconds
        self._started = 0.0
        self._phase = "starting"
        self._detail: str | None = None
        self._finished = False
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def __enter__(self) -> ProgressReporter:
        self._started = time.monotonic()
        self._emit("started", "starting", f"command={self.command}")
        self._thread = threading.Thread(
            target=self._heartbeat_loop,
            name=f"quality-runner-progress-{self.command}",
            daemon=True,
        )
        self._thread.start()
        return self

    def __exit__(self, exc_type: object, _exc_value: object, _traceback: object) -> bool:
        if exc_type is not None and not self._finished:
            self.finish("failed")
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
        return False

    def phase(self, name: str, detail: str | None = None) -> None:
        with self._lock:
            self._phase = name
            self._detail = detail
        self._emit("phase", name, detail)

    def finish(self, status: str) -> None:
        with self._lock:
            if self._finished:
                return
            self._finished = True
            phase = self._phase
        self._emit("complete", phase, f"status={status}")

    def _heartbeat_loop(self) -> None:
        while not self._stop_event.wait(self.interval_seconds):
            with self._lock:
                phase = self._phase
                detail = self._detail
            self._emit("heartbeat", phase, detail)

    def _emit(self, event: str, phase: str, detail: str | None) -> None:
        elapsed = time.monotonic() - self._started
        parts = [
            "[quality-runner]",
            f"event={event}",
            f"command={self.command}",
            f"phase={phase}",
            f"elapsed={elapsed:.1f}s",
        ]
        if detail:
            parts.append(detail)
        try:
            print(" ".join(parts), file=self.stream, flush=True)
        except OSError:
            # Progress must never turn a completed scan into a failed scan when
            # a caller closes or stops reading the diagnostic stream.
            return
