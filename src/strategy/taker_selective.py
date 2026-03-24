"""
Taker selective strategy module for the Polymarket BTC UpDown 5m trading bot.

This module provides a TakerSelectiveStrategy class to evaluate trading windows
and make trading decisions based on signals and filters.
"""

from dataclasses import dataclass
from typing import Optional

from src.config import CONFIG
from src.engine.state import BotState
from src.feeds.feed_manager import FeedManager
from src.signal.scorer import SignalScorer, SignalResult
from src.strategy.filters import should_trade
from src.strategy.kelly import calc_kelly_bet


@dataclass(slots=True)
class TradeDecision:
    """Dataclass representing a trading decision.

    Attributes:
        side: Side of the trade ("Up" or "Down").
        token_id: Token ID for the trade.
        price: Price of the token.
        size: Size of the trade in USDC.
        confidence: Confidence level of the signal.
    """

    side: str
    token_id: str
    price: float
    size: float
    confidence: float


class TakerSelectiveStrategy:
    """Class to evaluate trading windows and make trading decisions."""

    async def evaluate_window(
        self, feeds: FeedManager, signal_scorer: SignalScorer, state: BotState
    ) -> Optional[TradeDecision]:
        """Evaluate the current trading window and make a trading decision.

        Args:
            feeds: FeedManager containing the current feeds.
            signal_scorer: SignalScorer to score the trading signal.
            state: Current bot state.

        Returns:
            TradeDecision if a trade should be executed, None otherwise.
        """
        # Get the latest prices
        current_price = feeds.binance_feed.get_latest_price()
        price_to_beat = feeds.polymarket_rtds_feed.get_price_to_beat()

        if current_price is None or price_to_beat is None:
            return None

        # Calculate delta
        delta = (current_price - price_to_beat) / price_to_beat

        # Calculate volatility (using a fixed window for simplicity)
        volatility = 0.01  # Placeholder for actual volatility calculation

        # Calculate GBM probability
        time_remaining = 300  # Placeholder for actual time remaining
        gbm_prob = 0.5  # Placeholder for actual GBM probability

        # Calculate RSI and EMA spread (placeholders for actual calculations)
        rsi = 50.0
        ema_spread = 0.0

        # Score the signal
        signal: SignalResult = signal_scorer.score(
            delta=delta,
            volatility=volatility,
            gbm_prob=gbm_prob,
            rsi=rsi,
            ema_spread=ema_spread,
            time_remaining=time_remaining,
        )

        # Determine the best ask price based on the signal direction
        if signal.direction == "UP":
            best_ask = feeds.polymarket_clob_feed.get_best_ask("up_token_id")
        elif signal.direction == "DOWN":
            best_ask = feeds.polymarket_clob_feed.get_best_ask("down_token_id")
        else:
            best_ask = 0.0

        if best_ask is None:
            return None

        # Check if the trade should be executed
        should_execute, reason = should_trade(signal=signal, best_ask=best_ask, state=state)

        if not should_execute:
            return None

        # Calculate the Kelly bet size
        bet_size = calc_kelly_bet(
            win_rate=state.get_win_rate(),
            token_price=best_ask,
            bankroll=state.bankroll,
            fraction=CONFIG.KELLY_FRACTION,
        )

        if bet_size <= 0:
            return None

        # Create the trade decision
        trade_decision = TradeDecision(
            side=signal.suggested_side or "",
            token_id="up_token_id" if signal.direction == "UP" else "down_token_id",
            price=best_ask,
            size=bet_size,
            confidence=signal.confidence,
        )

        return trade_decision
