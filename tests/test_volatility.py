"""
Test module for volatility calculation.
"""

import time
from collections import deque

import numpy as np

from src.feeds.binance_ws import Tick
from src.signal.volatility import calc_rolling_volatility


def _make_ticks(prices: list[float], spacing_ms: int = 200) -> deque[Tick]:
    """Create a deque of Tick objects from a price list.

    Args:
        prices: List of prices.
        spacing_ms: Millisecond spacing between ticks.

    Returns:
        Deque of Tick objects.
    """
    now_ms = int(time.time() * 1000)
    ticks: deque[Tick] = deque(maxlen=600)
    for i, p in enumerate(prices):
        ticks.append(
            Tick(
                price=p,
                quantity=0.01,
                timestamp=now_ms - (len(prices) - i) * spacing_ms,
                is_buyer_maker=False,
            )
        )
    return ticks


def test_volatility_returns_hourly_not_annualized() -> None:
    """Volatility should be hourly, not annualized.

    For a 300s window, the hourly factor is sqrt(3600/300) = sqrt(12) ~ 3.46.
    Annualized factor would be sqrt(365*24*3600/300) ~ 324.5.
    So hourly vol should be ~94x smaller than annualized vol.
    """
    # Generate stable prices with small noise
    np.random.seed(42)
    base = 87000.0
    prices = [base + np.random.normal(0, 5) for _ in range(100)]
    ticks = _make_ticks(prices, spacing_ms=200)

    vol = calc_rolling_volatility(ticks, 300)

    # Hourly vol for BTC should be small (< 1%)
    # Annualized would be ~30-100%
    assert vol > 0.0, "Volatility should be > 0 with varying prices"
    assert vol < 0.05, f"Hourly vol should be < 5%, got {vol:.4f} (likely annualized if > 1)"


def test_volatility_zero_with_constant_prices() -> None:
    """Volatility should be 0 with constant prices."""
    prices = [87000.0] * 50
    ticks = _make_ticks(prices)
    vol = calc_rolling_volatility(ticks, 300)
    assert vol == 0.0


def test_volatility_zero_with_insufficient_data() -> None:
    """Volatility should be 0 with fewer than 2 ticks."""
    ticks: deque[Tick] = deque(maxlen=600)
    vol = calc_rolling_volatility(ticks, 300)
    assert vol == 0.0

    # Single tick
    ticks.append(
        Tick(
            price=87000.0,
            quantity=0.01,
            timestamp=int(time.time() * 1000),
            is_buyer_maker=False,
        )
    )
    vol = calc_rolling_volatility(ticks, 300)
    assert vol == 0.0
