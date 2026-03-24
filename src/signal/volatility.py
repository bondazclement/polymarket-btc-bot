"""
Volatility calculation module for the Polymarket BTC UpDown 5m trading bot.

This module provides functions to calculate the rolling volatility of BTC prices
using numpy for vectorized operations.
"""

import numpy as np
from collections import deque

from src.feeds.binance_ws import Tick


def calc_rolling_volatility(prices: deque[Tick], window_seconds: int) -> float:
    """Calculate the rolling volatility of BTC prices.

    Args:
        prices: Deque of Tick objects containing price data.
        window_seconds: Time window in seconds for volatility calculation.

    Returns:
        Annualized volatility as a float.
    """
    if len(prices) < 2:
        return 0.0

    # Convert deque of Tick objects to numpy array of prices
    price_array = np.array([tick.price for tick in prices])

    # Calculate log returns
    log_returns = np.diff(np.log(price_array))

    # Calculate standard deviation of log returns
    std_log_returns = np.std(log_returns)

    # Annualize the volatility
    annualization_factor = np.sqrt((3600 * 24 * 365) / window_seconds)
    annualized_volatility = std_log_returns * annualization_factor

    return annualized_volatility
