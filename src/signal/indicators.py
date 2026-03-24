"""
Indicators module for the Polymarket BTC UpDown 5m trading bot.

This module provides functions to calculate technical indicators such as RSI and EMA spread
using numpy for vectorized operations.
"""

import numpy as np


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

    # Calculate price changes
    deltas = np.diff(prices)

    # Separate gains and losses
    gains = deltas[deltas > 0]
    losses = -deltas[deltas < 0]

    # Calculate average gains and losses
    avg_gain = np.mean(gains[:period])
    avg_loss = np.mean(losses[:period])

    # Smooth the averages
    for i in range(period, len(deltas)):
        delta = deltas[i]
        if delta > 0:
            avg_gain = (avg_gain * (period - 1) + delta) / period
            avg_loss = (avg_loss * (period - 1)) / period
        else:
            avg_gain = (avg_gain * (period - 1)) / period
            avg_loss = (avg_loss * (period - 1) - delta) / period

    # Calculate Relative Strength (RS)
    rs = avg_gain / avg_loss if avg_loss != 0 else 0.0

    # Calculate RSI
    rsi = 100.0 - (100.0 / (1.0 + rs))

    return rsi


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

    # Calculate fast EMA
    ema_fast = np.zeros_like(prices)
    ema_fast[fast - 1] = np.mean(prices[:fast])
    for i in range(fast, len(prices)):
        ema_fast[i] = (prices[i] * (2.0 / (fast + 1))) + (ema_fast[i - 1] * (1 - (2.0 / (fast + 1))))

    # Calculate slow EMA
    ema_slow = np.zeros_like(prices)
    ema_slow[slow - 1] = np.mean(prices[:slow])
    for i in range(slow, len(prices)):
        ema_slow[i] = (prices[i] * (2.0 / (slow + 1))) + (ema_slow[i - 1] * (1 - (2.0 / (slow + 1))))

    # Calculate spread
    spread = ema_fast[-1] - ema_slow[-1]

    # Normalize spread by the average price
    avg_price = np.mean(prices)
    normalized_spread = spread / avg_price if avg_price != 0 else 0.0

    return normalized_spread
