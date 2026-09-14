"""Rolling-window Bz rate-of-change, backed by Polars for the point-in-time lookup."""

from collections import deque
from datetime import datetime, timedelta

import polars as pl


class RollingWindow:
    """Tracks recent Bz samples and derives dBz/dt over a trailing lookback.

    A sharp southward drop in Bz (large negative dBz/dt) often precedes a
    storm's main phase, so this is tracked independently of the instantaneous
    Bz value used by the classifier.
    """

    def __init__(self, window_minutes: int = 20, lookback_minutes: int = 15) -> None:
        self._window = timedelta(minutes=window_minutes)
        self._lookback = timedelta(minutes=lookback_minutes)
        self._buffer: deque[tuple[datetime, float]] = deque()

    def push_and_get_derivative(self, timestamp: datetime, bz: float) -> float:
        """Record a new sample and return dBz/dt (nT/min) over the lookback window."""
        self._buffer.append((timestamp, bz))
        cutoff = timestamp - self._window
        while self._buffer and self._buffer[0][0] < cutoff:
            self._buffer.popleft()

        if len(self._buffer) < 2:
            return 0.0

        frame = pl.DataFrame(
            {
                "timestamp": [t for t, _ in self._buffer],
                "bz": [b for _, b in self._buffer],
            }
        ).sort("timestamp")

        target = timestamp - self._lookback
        anchor = frame.filter(pl.col("timestamp") <= target).tail(1)
        if anchor.is_empty():
            anchor = frame.head(1)  # insufficient history yet: fall back to oldest sample

        anchor_time: datetime = anchor["timestamp"][0]
        anchor_bz: float = anchor["bz"][0]
        elapsed_minutes = (timestamp - anchor_time).total_seconds() / 60.0
        if elapsed_minutes <= 0:
            return 0.0
        return (bz - anchor_bz) / elapsed_minutes
