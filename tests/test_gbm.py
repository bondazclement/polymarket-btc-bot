"""
Test module for the GBM probability calculation functions.
"""

import pytest

from src.signal.gbm import calc_up_probability


def test_calc_up_probability_large_positive_delta():
    """Test calc_up_probability with a large positive delta and little time remaining."""
    delta = 0.1  # Large positive delta
    volatility_hourly = 0.01
    time_remaining_sec = 10  # Little time remaining
    probability = calc_up_probability(delta, volatility_hourly, time_remaining_sec)
    assert probability == pytest.approx(1.0, abs=0.01)


def test_calc_up_probability_zero_delta():
    """Test calc_up_probability with zero delta."""
    delta = 0.0
    volatility_hourly = 0.01
    time_remaining_sec = 300
    probability = calc_up_probability(delta, volatility_hourly, time_remaining_sec)
    assert probability == pytest.approx(0.5, abs=0.01)


def test_calc_up_probability_large_negative_delta():
    """Test calc_up_probability with a large negative delta."""
    delta = -0.1  # Large negative delta
    volatility_hourly = 0.01
    time_remaining_sec = 300
    probability = calc_up_probability(delta, volatility_hourly, time_remaining_sec)
    assert probability == pytest.approx(0.0, abs=0.01)


def test_calc_up_probability_zero_time_remaining_positive_delta():
    """Test calc_up_probability with zero time remaining and positive delta."""
    delta = 0.01
    volatility_hourly = 0.01
    time_remaining_sec = 0
    probability = calc_up_probability(delta, volatility_hourly, time_remaining_sec)
    assert probability == 1.0


def test_calc_up_probability_zero_time_remaining_negative_delta():
    """Test calc_up_probability with zero time remaining and negative delta."""
    delta = -0.01
    volatility_hourly = 0.01
    time_remaining_sec = 0
    probability = calc_up_probability(delta, volatility_hourly, time_remaining_sec)
    assert probability == 0.0
