"""
Taker selective strategy module for the Polymarket BTC UpDown 5m trading bot.

This module provides a TakerSelectiveStrategy class to evaluate trading windows
and make trading decisions based on signals and filters.
"""

from dataclasses import dataclass
from typing import Optional

import numpy as np
from structlog import get_logger

from src.config import CONFIG


logger = get_logger(__name__)
from src.engine.clock import get_time_remaining
from src.engine.state import BotState
from src.feeds.feed_manager import FeedManager
from src.signal.delta import calc_delta
from src.signal.gbm import calc_up_probability
from src.signal.indicators import calc_rsi, calc_ema_spread
from src.signal.scorer import SignalScorer, SignalResult
from src.signal.volatility import calc_rolling_volatility
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
        self,
        feeds: FeedManager,
        signal_scorer: SignalScorer,
        state: BotState,
        up_token_id: str = "",
        down_token_id: str = "",
    ) -> Optional[TradeDecision]:
        """Evaluate the current trading window and make a trading decision.

        Args:
            feeds: FeedManager containing the current feeds.
            signal_scorer: SignalScorer to score the trading signal.
            state: Current bot state.
            up_token_id: Token ID for the Up token.
            down_token_id: Token ID for the Down token.

        Returns:
            TradeDecision if a trade should be executed, None otherwise.
        """
        # Get the latest prices
        current_price = feeds.binance_feed.get_latest_price()
        price_to_beat = feeds.polymarket_rtds_feed.get_price_to_beat()

        if current_price == 0.0 or price_to_beat is None:
            logger.info("Skip: missing price data", current_price=current_price, price_to_beat=price_to_beat)
            return None

        # Calculate delta
        delta = calc_delta(current_price, price_to_beat)

        # Calculate time remaining in window
        time_remaining = get_time_remaining()

        # Calculate volatility on the last 300 seconds of ticks
        tick_buffer = feeds.binance_feed.get_price_buffer()
        volatility_hourly = calc_rolling_volatility(tick_buffer, 300)

        # Need enough ticks for indicators
        if len(tick_buffer) < 20:
            logger.info("Skip: insufficient ticks", tick_count=len(tick_buffer))
            return None

        # Extract prices as numpy array for indicators
        price_array = np.array([t.price for t in tick_buffer])

        # Calculate real signal values
        gbm_prob = calc_up_probability(delta, volatility_hourly, time_remaining)
        rsi = calc_rsi(price_array)
        ema_spread = calc_ema_spread(price_array)

        # Score the signal
        signal: SignalResult = signal_scorer.score(
            delta=delta,
            volatility=volatility_hourly,
            gbm_prob=gbm_prob,
            rsi=rsi,
            ema_spread=ema_spread,
            time_remaining=time_remaining,
        )

        logger.info(
            "Signal evaluated",
            delta=delta,
            volatility_hourly=volatility_hourly,
            gbm_prob=gbm_prob,
            rsi=rsi,
            ema_spread=ema_spread,
            time_remaining=time_remaining,
            direction=signal.direction,
            confidence=signal.confidence,
        )

        # Determine the best ask price based on the signal direction
        if signal.direction == "UP":
            best_ask = feeds.polymarket_clob_feed.get_best_ask(up_token_id)
        elif signal.direction == "DOWN":
            best_ask = feeds.polymarket_clob_feed.get_best_ask(down_token_id)
        else:
            best_ask = 0.0

        if best_ask is None:
            logger.info("Skip: no best_ask available", direction=signal.direction)
            return None

        # Check if the trade should be executed
        should_execute, reason = should_trade(signal=signal, best_ask=best_ask, state=state)

        if not should_execute:
            logger.info("Skip: filter rejected", reason=reason, best_ask=best_ask, direction=signal.direction)
            return None

        # Use bootstrap win rate until we have enough history
        win_rate = state.get_win_rate()
        if state.total_trades < 20:
            win_rate = max(win_rate, CONFIG.BOOTSTRAP_WIN_RATE)

        # Calculate the Kelly bet size
        bet_size = calc_kelly_bet(
            win_rate=win_rate,
            token_price=best_ask,
            bankroll=state.bankroll,
            fraction=CONFIG.KELLY_FRACTION,
        )

        if bet_size <= 0:
            logger.info("Skip: Kelly bet_size <= 0", win_rate=win_rate, best_ask=best_ask)
            return None

        # Create the trade decision
        token_id = up_token_id if signal.direction == "UP" else down_token_id
        trade_decision = TradeDecision(
            side=signal.suggested_side or "",
            token_id=token_id,
            price=best_ask,
            size=bet_size,
            confidence=signal.confidence,
        )

        return trade_decision
