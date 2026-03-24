"""
Kelly criterion module for the Polymarket BTC UpDown 5m trading bot.

This module provides functions to calculate the optimal bet size using the Kelly criterion.
"""

from src.config import CONFIG


def calc_kelly_bet(win_rate: float, token_price: float, bankroll: float, fraction: float = 0.25) -> float:
    """Calculate the optimal bet size using the Kelly criterion.

    Args:
        win_rate: Win rate as a float between 0.0 and 1.0.
        token_price: Current token price.
        bankroll: Current available bankroll in USDC.
        fraction: Fraction of the Kelly criterion to use (default: 0.25).

    Returns:
        Optimal bet size in USDC.
    """
    # Calculate the Kelly fraction
    kelly_fraction = (win_rate * (1.0 / token_price - 1.0) - (1.0 - win_rate)) / (1.0 / token_price - 1.0)

    # If Kelly fraction is negative, do not bet
    if kelly_fraction <= 0:
        return 0.0

    # Calculate the bet size
    bet_size = kelly_fraction * fraction * bankroll

    # Cap the bet size at 5% of the bankroll
    bet_size = min(bet_size, bankroll * 0.05)

    # Ensure the bet size is at least 2.50 USDC (minimum Polymarket order size)
    if bet_size > 0:
        bet_size = max(bet_size, 2.50)

    return bet_size
