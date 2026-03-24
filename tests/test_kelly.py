"""
Test module for the Kelly criterion calculation functions.
"""

import pytest

from src.strategy.kelly import calc_kelly_bet


def test_calc_kelly_bet_positive_edge():
    """Test calc_kelly_bet with a positive edge."""
    win_rate = 0.7
    token_price = 0.55
    bankroll = 100.0
    bet_size = calc_kelly_bet(win_rate, token_price, bankroll)
    assert bet_size > 0


def test_calc_kelly_bet_negative_edge():
    """Test calc_kelly_bet with a negative edge."""
    win_rate = 0.4
    token_price = 0.55
    bankroll = 100.0
    bet_size = calc_kelly_bet(win_rate, token_price, bankroll)
    assert bet_size == 0.0


def test_calc_kelly_bet_exact_amount():
    """Test calc_kelly_bet with specific values to verify the exact amount."""
    win_rate = 0.7
    token_price = 0.55
    bankroll = 100.0
    fraction = 0.25
    bet_size = calc_kelly_bet(win_rate, token_price, bankroll, fraction)
    expected_bet_size = ((0.7 * (1.0 / 0.55 - 1.0) - (1.0 - 0.7)) / (1.0 / 0.55 - 1.0)) * 0.25 * 100.0
    assert bet_size == pytest.approx(min(expected_bet_size, bankroll * 0.05), rel=1e-6)


def test_calc_kelly_bet_cap_at_5_percent():
    """Test calc_kelly_bet to ensure it does not exceed 5% of the bankroll."""
    win_rate = 0.9
    token_price = 0.1
    bankroll = 100.0
    bet_size = calc_kelly_bet(win_rate, token_price, bankroll)
    assert bet_size <= bankroll * 0.05


def test_calc_kelly_bet_minimum_amount():
    """Test calc_kelly_bet to ensure it meets the minimum order size."""
    win_rate = 0.6
    token_price = 0.5
    bankroll = 10.0
    bet_size = calc_kelly_bet(win_rate, token_price, bankroll)
    assert bet_size >= 2.50
