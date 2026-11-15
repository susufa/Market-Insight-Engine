"""
tests/unit/test_time_series_splitter.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Unit tests for the TimeSeriesSplitter and purging/embargo logic.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from models.validation.splitter import TimeSeriesSplitter


def test_splitter_expanding_chronology_and_gap() -> None:
    splitter = TimeSeriesSplitter(
        min_train_size=100,
        test_size=20,
        step_size=20,
        gap_size=5,
        mode="expanding",
    )
    n_samples = 200
    n_splits = splitter.get_n_splits(n_samples)
    assert n_splits > 0

    folds = list(splitter.split(n_samples))
    assert len(folds) == n_splits

    prev_train_end = 0
    for _fold_i, (train_idx, test_idx) in enumerate(folds):
        # 1. Train must strictly precede test
        assert max(train_idx) < min(test_idx)

        # 2. Embargo gap between train end and test start
        train_end = max(train_idx) + 1
        test_start = min(test_idx)
        assert test_start - train_end == 5

        # 3. Expanding mode: train_idx starts at 0 and grows
        assert train_idx[0] == 0
        assert len(train_idx) >= splitter.min_train_size
        assert len(train_idx) >= prev_train_end
        prev_train_end = len(train_idx)

        # 4. Test size matches
        assert len(test_idx) == 20


def test_splitter_rolling_mode() -> None:
    splitter = TimeSeriesSplitter(
        min_train_size=50,
        test_size=10,
        step_size=10,
        gap_size=3,
        mode="rolling",
    )
    n_samples = 120
    folds = list(splitter.split(n_samples))
    assert len(folds) >= 3

    for train_idx, test_idx in folds:
        assert max(train_idx) < min(test_idx)
        assert min(test_idx) - (max(train_idx) + 1) == 3
        # In rolling mode, train size is capped at min_train_size
        assert len(train_idx) == 50


def test_splitter_by_dates() -> None:
    start = datetime(2023, 1, 1, tzinfo=UTC)
    dates = [start + timedelta(days=i) for i in range(150)]

    splitter = TimeSeriesSplitter(
        min_train_size=60,
        test_size=20,
        step_size=20,
        gap_size=4,
    )
    date_folds = list(splitter.split_by_dates(dates))
    assert len(date_folds) > 0

    for train_d, test_d in date_folds:
        assert max(train_d) < min(test_d)
        assert (min(test_d) - max(train_d)).days >= 4


def test_splitter_insufficient_samples_raises() -> None:
    splitter = TimeSeriesSplitter(min_train_size=100, test_size=30, gap_size=5)
    assert splitter.get_n_splits(50) == 0

    with pytest.raises(ValueError, match="Insufficient sample length"):
        list(splitter.split(50))
