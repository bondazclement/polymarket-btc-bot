"""
Indicators module for the Polymarket BTC UpDown 5m trading bot.

This module provides functions to calculate technical indicators such as RSI and EMA spread
using numpy for vectorized operations.
"""

import numpy as np


def calc_ema(prices: np.ndarray, period: int) -> np.ndarray:
    """Calculate the Exponential Moving Average (EMA) for the given prices.

    Args:
        prices: Numpy array of price data.
        period: Period for EMA calculation.

    Returns:
        Numpy array of EMA values.
    """
    alpha = 2.0 / (period + 1)
    result = np.empty_like(prices)
    result[0] = prices[0]
    # EMA is intrinsically recursive; a scalar loop is acceptable here
    for i in range(1, len(prices)):
        result[i] = alpha * prices[i] + (1 - alpha) * result[i - 1]
    return result


def calc_rsi(prices: np.ndarray, period: int = 14) -> float:
    """Calculate the Relative Strength Index (RSI) for the given prices.

    Args:
        prices: Numpy array of price data.
        period: Period for RSI calculation (default: 14).

    Returns:
        RSI value as a float.
    """
    if len(prices) < period + 1:
        return 50.0

    deltas = np.diff(prices)
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)

    avg_gain = np.mean(gains[:period])
    avg_loss = np.mean(losses[:period])

    if avg_loss == 0:
        return 100.0

    rs = avg_gain / avg_loss
    return float(100.0 - (100.0 / (1.0 + rs)))


def calc_ema_spread(prices: np.ndarray, fast: int = 5, slow: int = 20) -> float:
    """Calculate the spread between fast and slow Exponential Moving Averages (EMA).

    Args:
        prices: Numpy array of price data.
        fast: Period for fast EMA (default: 5).
        slow: Period for slow EMA (default: 20).

    Returns:
        Normalized EMA spread as a float.
    """
    if len(prices) < max(fast, slow):
        return 0.0

    ema_fast = calc_ema(prices, fast)
    ema_slow = calc_ema(prices, slow)

    spread = ema_fast[-1] - ema_slow[-1]

    avg_price = np.mean(prices)
    normalized_spread = float(spread / avg_price) if avg_price != 0 else 0.0

    return normalized_spread
