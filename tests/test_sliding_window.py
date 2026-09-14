from datetime import datetime, timedelta, timezone

import pytest

from src.analytics.sliding_window import RollingWindow

T0 = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)


def test_derivative_matches_known_linear_slope():
    window = RollingWindow(window_minutes=25, lookback_minutes=15)
    derivative = None
    for minute in range(21):
        bz = -5.0 - minute  # decreasing 1 nT per minute
        derivative = window.push_and_get_derivative(T0 + timedelta(minutes=minute), bz)

    assert derivative == pytest.approx(-1.0)


def test_derivative_is_zero_with_a_single_sample():
    window = RollingWindow()
    assert window.push_and_get_derivative(T0, -5.0) == 0.0


def test_derivative_is_zero_when_anchor_and_latest_share_a_timestamp():
    window = RollingWindow()
    window.push_and_get_derivative(T0, -5.0)
    assert window.push_and_get_derivative(T0, -8.0) == 0.0


def test_derivative_falls_back_to_oldest_sample_when_history_is_short():
    window = RollingWindow(window_minutes=25, lookback_minutes=15)
    window.push_and_get_derivative(T0, -5.0)
    derivative = window.push_and_get_derivative(T0 + timedelta(minutes=5), -10.0)
    # Only 5 minutes of history exist; falls back to the oldest sample (t=0)
    assert derivative == pytest.approx(-1.0)


def test_old_samples_are_pruned_from_the_window():
    window = RollingWindow(window_minutes=10, lookback_minutes=5)
    window.push_and_get_derivative(T0, -5.0)
    # Jump far enough ahead that the first sample falls outside the window
    derivative = window.push_and_get_derivative(T0 + timedelta(minutes=30), -8.0)
    # With no in-window history before the lookback target, falls back to itself -> 0
    assert derivative == pytest.approx(0.0)
