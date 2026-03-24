"""
Filters module for the Polymarket BTC UpDown 5m trading bot.

This module provides functions to filter trading signals based on various conditions.
"""

from src.config import CONFIG
from src.engine.state import BotState
from src.signal.scorer import SignalResult


def should_trade(signal: SignalResult, best_ask: float, state: BotState) -> tuple[bool, str]:
    """Determine if a trade should be executed based on the signal and current state.

    Args:
        signal: SignalResult containing the signal direction and confidence.
        best_ask: Best ask price for the token.
        state: Current bot state.

    Returns:
        Tuple containing a boolean indicating whether to trade and a reason string.
    """
    # Check if the signal direction is not SKIP
    if signal.direction == "SKIP":
        return False, "Signal direction is SKIP"

    # Check if the best ask price is within the maximum allowed price
    if best_ask > CONFIG.MAX_TOKEN_PRICE:
        return False, f"Best ask price {best_ask} exceeds maximum allowed price {CONFIG.MAX_TOKEN_PRICE}"

    # Check if the signal confidence is sufficient
    if signal.confidence < 0.6:
        return False, f"Signal confidence {signal.confidence} is below the required threshold of 0.6"

    # Check if there is an open position
    if state.current_position is not None:
        return False, "There is already an open position"

    # Check if the stop loss has been hit
    if state.current_position is not None and state.is_stop_loss_hit(best_ask, state.current_position):
        return False, "Stop loss has been hit"

    # All conditions are met, proceed with the trade
    return True, "All conditions are met"
