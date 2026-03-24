"""
Delta calculation module for the Polymarket BTC UpDown 5m trading bot.

This module provides functions to calculate the delta between the current price
and the opening price, and to determine the direction based on the delta.
"""

from src.config import CONFIG


def calc_delta(current_price: float, open_price: float) -> float:
    """Calculate the delta between the current price and the opening price.

    Args:
        current_price: Current price of BTC.
        open_price: Opening price of BTC.

    Returns:
        Delta as a percentage.
    """
    return (current_price - open_price) / open_price


def calc_delta_direction(delta: float) -> str:
    """Determine the direction based on the delta.

    Args:
        delta: Delta as a percentage.

    Returns:
        Direction as a string: "UP", "DOWN", or "NEUTRAL".
    """
    if delta > CONFIG.DELTA_MIN:
        return "UP"
    elif delta < -CONFIG.DELTA_MIN:
        return "DOWN"
    else:
        return "NEUTRAL"
