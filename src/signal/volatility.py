"""
Volatility calculation module for the Polymarket BTC UpDown 5m trading bot.

This module provides functions to calculate the rolling volatility of BTC prices
using numpy for vectorized operations.
"""

import time
from collections import deque

import numpy as np

from src.feeds.binance_ws import Tick


def calc_rolling_volatility(prices: deque[Tick], window_seconds: int) -> float:
    """Calculate the rolling volatility of BTC prices within a time window.

    Args:
        prices: Deque of Tick objects containing price data.
        window_seconds: Time window in seconds for volatility calculation.

    Returns:
        Hourly volatility as a float (suitable for GBM with t in hours).
    """
    if len(prices) < 2:
        return 0.0

    cutoff_ms = int((time.time() - window_seconds) * 1000)
    recent_prices = [t.price for t in prices if t.timestamp >= cutoff_ms]

    if len(recent_prices) < 2:
        return 0.0

    price_array = np.array(recent_prices)
    log_returns = np.diff(np.log(price_array))
    std_log_returns = np.std(log_returns)

    hourly_factor = np.sqrt(3600 / window_seconds)
    return float(std_log_returns * hourly_factor)
