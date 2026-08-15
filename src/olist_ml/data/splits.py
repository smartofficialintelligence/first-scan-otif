"""Chronological train / validation / test / replay splits."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class SplitFrames:
    train: pd.DataFrame
    validation: pd.DataFrame
    test: pd.DataFrame
    replay_holdout: pd.DataFrame
    cutoffs: dict[str, pd.Timestamp | None]


def temporal_split(
    frame: pd.DataFrame,
    *,
    time_col: str = "prediction_ts",
    valid_fraction: float = 0.15,
    test_fraction: float = 0.15,
    replay_fraction: float = 0.10,
) -> SplitFrames:
    """
    Split by time ascending.

    Earliest → train, then validation, test, latest → replay_holdout.
    Fractions apply to row counts after sorting (locked decision defaults).
    """
    if frame.empty:
        empty = frame.copy()
        return SplitFrames(empty, empty, empty, empty, {})

    if valid_fraction + test_fraction + replay_fraction >= 1.0:
        raise ValueError("valid+test+replay fractions must leave room for train")

    ordered = frame.sort_values(time_col).reset_index(drop=True)
    n = len(ordered)
    n_replay = max(1, int(n * replay_fraction)) if n > 10 else max(0, int(n * replay_fraction))
    n_test = max(1, int(n * test_fraction)) if n > 10 else max(0, int(n * test_fraction))
    n_valid = max(1, int(n * valid_fraction)) if n > 10 else max(0, int(n * valid_fraction))
    n_train = n - n_replay - n_test - n_valid
    if n_train < 1:
        # Tiny fixture fallback: put almost everything in train.
        n_train = max(1, n - 3)
        n_valid = 1 if n > 1 else 0
        n_test = 1 if n > 2 else 0
        n_replay = n - n_train - n_valid - n_test

    i0 = n_train
    i1 = i0 + n_valid
    i2 = i1 + n_test

    train = ordered.iloc[:i0].copy()
    validation = ordered.iloc[i0:i1].copy()
    test = ordered.iloc[i1:i2].copy()
    replay = ordered.iloc[i2:].copy()

    def _edge(df: pd.DataFrame) -> pd.Timestamp | None:
        return None if df.empty else pd.Timestamp(df[time_col].iloc[-1])

    cutoffs = {
        "train_end": _edge(train),
        "valid_end": _edge(validation),
        "test_end": _edge(test),
        "replay_end": _edge(replay),
    }
    return SplitFrames(train, validation, test, replay, cutoffs)
