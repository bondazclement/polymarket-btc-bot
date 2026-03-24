"""
State management module for the Polymarket BTC UpDown 5m trading bot.

This module defines the BotState dataclass and related methods for tracking
bankroll, trades, and performance metrics.
"""

from collections import deque
from dataclasses import dataclass


@dataclass(slots=True)
class BotState:
    """State dataclass for the trading bot.

    Attributes:
        bankroll: Current available bankroll in USDC.
        total_trades: Total number of trades executed.
        wins: Number of winning trades.
        losses: Number of losing trades.
        current_position: Current position (token ID or None).
        pnl_history: Deque of P&L values for recent trades.
    """

    bankroll: float
    total_trades: int
    wins: int
    losses: int
    current_position: str | None
    pnl_history: deque[float]

    def __post_init__(self) -> None:
        """Initialize the P&L history deque with a max length of 100."""
        self.pnl_history = deque(maxlen=100)

    def update_after_trade(self, pnl: float, is_win: bool) -> None:
        """Update the bot state after a trade.

        Args:
            pnl: Profit and loss from the trade.
            is_win: Whether the trade was a win.
        """
        self.bankroll += pnl
        self.total_trades += 1
        if is_win:
            self.wins += 1
        else:
            self.losses += 1
        self.pnl_history.append(pnl)

    def get_win_rate(self) -> float:
        """Calculate the win rate.

        Returns:
            Win rate as a float between 0 and 1.
        """
        if self.total_trades == 0:
            return 0.0
        return self.wins / self.total_trades

    def get_kelly_size(self, edge: float, price: float) -> float:
        """Calculate the Kelly criterion bet size.

        Args:
            edge: Edge (win_rate - price).
            price: Current token price.

        Returns:
            Kelly bet size.
        """
        if edge <= 0:
            return 0.0
        return (edge / (1.0 / price - 1.0)) * 0.25

    def is_stop_loss_hit(self, initial_bankroll: float = 100.0) -> bool:
        """Check if the stop loss threshold has been hit based on bankroll drawdown.

        Args:
            initial_bankroll: Initial bankroll to compare against (default: 100.0).

        Returns:
            True if stop loss is hit, False otherwise.
        """
        if initial_bankroll <= 0:
            return False
        loss_pct = (initial_bankroll - self.bankroll) / initial_bankroll
        return loss_pct >= 0.20
