"""
models/validation/splitter.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Strict time-series walk-forward cross-validation splitter.

Design rules:
- Chronological ordering is strictly preserved: no shuffling.
- Purging and Embargo: gap_size prevents overlapping label leakage when
  target horizon > 1 bar.
- Supports both Expanding Window (cumulative history) and Rolling Window
  (fixed lookback).
"""

from __future__ import annotations

from collections.abc import Generator
from datetime import datetime
from typing import Literal


class TimeSeriesSplitter:
    """
    Purged and Embargoed Walk-Forward Time Series Splitter.

    Parameters
    ----------
    min_train_size : int
        Minimum number of bars required for the first training window.
    test_size : int
        Number of bars in each out-of-sample test fold.
    step_size : int | None
        Step size by which to advance the test window. If None, defaults to test_size.
    gap_size : int
        Number of bars to drop between train and test sets to prevent label overlap
        (Purging / Embargo). Recommended to be >= (horizon - 1).
    mode : Literal["expanding", "rolling"]
        "expanding" keeps all historical bars up to the split point.
        "rolling" maintains a fixed training window of length `min_train_size`.
    """

    def __init__(
        self,
        min_train_size: int = 252,
        test_size: int = 63,
        step_size: int | None = None,
        gap_size: int = 5,
        mode: Literal["expanding", "rolling"] = "expanding",
    ) -> None:
        if min_train_size <= 0:
            raise ValueError(f"min_train_size must be positive, got {min_train_size}")
        if test_size <= 0:
            raise ValueError(f"test_size must be positive, got {test_size}")
        if gap_size < 0:
            raise ValueError(f"gap_size cannot be negative, got {gap_size}")

        self.min_train_size = min_train_size
        self.test_size = test_size
        self.step_size = step_size if step_size is not None else test_size
        self.gap_size = gap_size
        self.mode = mode

    def get_n_splits(self, n_samples: int) -> int:
        """Calculate the total number of walk-forward folds."""
        available = n_samples - self.min_train_size - self.gap_size
        if available < self.test_size:
            return 0
        return 1 + (available - self.test_size) // self.step_size

    def split(
        self,
        n_samples: int,
    ) -> Generator[tuple[list[int], list[int]], None, None]:
        """
        Generate (train_indices, test_indices) for each walk-forward fold.

        Yields
        ------
        train_indices : list[int]
        test_indices  : list[int]
        """
        n_splits = self.get_n_splits(n_samples)
        if n_splits == 0:
            raise ValueError(
                f"Insufficient sample length ({n_samples}) for min_train_size="
                f"{self.min_train_size}, gap_size={self.gap_size}, test_size={self.test_size}."
            )

        for i in range(n_splits):
            test_start = self.min_train_size + self.gap_size + i * self.step_size
            test_end = min(n_samples, test_start + self.test_size)

            train_end = test_start - self.gap_size

            train_start = 0 if self.mode == "expanding" else max(0, train_end - self.min_train_size)

            train_indices = list(range(train_start, train_end))
            test_indices = list(range(test_start, test_end))

            # Defensive assertion: train and test must have zero intersection
            # and train must strictly precede test
            if max(train_indices) >= min(test_indices):
                raise RuntimeError(
                    f"Chronology invariant violated: max(train)={max(train_indices)} >= "
                    f"min(test)={min(test_indices)}"
                )

            yield train_indices, test_indices

    def split_by_dates(
        self,
        dates: list[datetime],
    ) -> Generator[tuple[list[datetime], list[datetime]], None, None]:
        """Convenience method to yield slices of datetime timestamps."""
        if any(dates[i] >= dates[i + 1] for i in range(len(dates) - 1)):
            raise ValueError("Input dates must be strictly monotonically increasing.")
        n_samples = len(dates)
        for train_idx, test_idx in self.split(n_samples):
            yield (
                [dates[i] for i in train_idx],
                [dates[i] for i in test_idx],
            )
