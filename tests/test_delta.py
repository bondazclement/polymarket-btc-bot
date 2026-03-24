"""
Test module for the delta calculation functions.
"""

import pytest

from src.signal.delta import calc_delta, calc_delta_direction


def test_calc_delta_positive():
    """Test calc_delta with a positive delta."""
    current_price = 50000.0
    open_price = 49000.0
    delta = calc_delta(current_price, open_price)
    assert delta == pytest.approx(0.020408163, rel=1e-6)


def test_calc_delta_negative():
    """Test calc_delta with a negative delta."""
    current_price = 49000.0
    open_price = 50000.0
    delta = calc_delta(current_price, open_price)
    assert delta == pytest.approx(-0.02, rel=1e-6)


def test_calc_delta_zero():
    """Test calc_delta with zero delta."""
    current_price = 50000.0
    open_price = 50000.0
    delta = calc_delta(current_price, open_price)
    assert delta == 0.0


def test_calc_delta_direction_up():
    """Test calc_delta_direction with a positive delta above the threshold."""
    delta = 0.001  # Above DELTA_MIN (0.0003)
    direction = calc_delta_direction(delta)
    assert direction == "UP"


def test_calc_delta_direction_down():
    """Test calc_delta_direction with a negative delta below the threshold."""
    delta = -0.001  # Below -DELTA_MIN (-0.0003)
    direction = calc_delta_direction(delta)
    assert direction == "DOWN"


def test_calc_delta_direction_neutral():
    """Test calc_delta_direction with a delta within the neutral range."""
    delta = 0.0001  # Within [-DELTA_MIN, DELTA_MIN]
    direction = calc_delta_direction(delta)
    assert direction == "NEUTRAL"
