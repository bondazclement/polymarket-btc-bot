"""
Geometric Brownian Motion (GBM) module for the Polymarket BTC UpDown 5m trading bot.

This module provides functions to calculate the probability of BTC price going up
using the GBM model.
"""

from scipy.stats import norm


def calc_up_probability(delta: float, volatility_hourly: float, time_remaining_sec: float) -> float:
    """Calculate the probability of BTC price going up using the GBM model.

    Args:
        delta: Delta as a percentage.
        volatility_hourly: Hourly volatility of BTC.
        time_remaining_sec: Time remaining in the current 5-minute window in seconds.

    Returns:
        Probability of BTC price going up as a float between 0.0 and 1.0.
    """
    if time_remaining_sec < 1:
        return 1.0 if delta > 0 else 0.0

    # Calculate the z-score
    z = delta / (volatility_hourly * (time_remaining_sec / 3600) ** 0.5)

    # Calculate the probability using the cumulative distribution function (CDF)
    probability = norm.cdf(z)

    return probability
