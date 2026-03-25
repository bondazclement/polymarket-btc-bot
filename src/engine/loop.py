"""
Trading loop module for the Polymarket BTC UpDown 5m trading bot.

This module provides the main trading loop that runs indefinitely,
executing one iteration per 5-minute trading window.
"""

import asyncio
from typing import Optional

from structlog import get_logger

from src.config import CONFIG
from src.engine.clock import get_time_remaining, get_window_start, sleep_until
from src.engine.state import BotState
from src.execution.clob_client import PolymarketClient
from src.execution.order_builder import build_and_post_order
from src.execution.redeemer import redeem_if_resolved
from src.execution.slug_resolver import get_current_slug, resolve_market_data
from src.feeds.feed_manager import FeedManager
from src.signal.scorer import SignalScorer
from src.strategy.taker_selective import TakerSelectiveStrategy, TradeDecision


logger = get_logger(__name__)


class TradingLoop:
    """Main trading loop for the Polymarket BTC UpDown 5m trading bot.

    Attributes:
        state: Current bot state.
        feeds: FeedManager for managing WebSocket feeds.
        strategy: TakerSelectiveStrategy for making trading decisions.
        signal_scorer: SignalScorer for scoring trading signals.
        clob_client: PolymarketClient for interacting with the CLOB.
        mode: Trading mode ("dry-run" or "safe").
    """

    def __init__(self, state: BotState, mode: str = "dry-run") -> None:
        """Initialize the TradingLoop with the given state and mode.

        Args:
            state: Current bot state.
            mode: Trading mode ("dry-run" or "safe").
        """
        self.state = state
        self.feeds = FeedManager()
        self.strategy = TakerSelectiveStrategy()
        self.signal_scorer = SignalScorer()
        self.clob_client = PolymarketClient()
        self.mode = mode

    async def run(self) -> None:
        """Run the main trading loop indefinitely."""
        await self.feeds.start_all()

        while True:
            try:
                await self._run_window()
            except Exception as e:
                logger.error("Error in trading window", error=str(e))
                await asyncio.sleep(5)

    async def _run_window(self) -> None:
        """Run a single trading window iteration."""
        # Wait for the start of the next window
        remaining = get_time_remaining()
        if remaining > 5:
            await asyncio.sleep(remaining + 1)

        # T=0 : Record the opening Chainlink price
        window_start = get_window_start()
        logger.info("New window started", window_start=window_start)

        price_to_beat = self.feeds.polymarket_rtds_feed.get_price_to_beat()
        if price_to_beat is None:
            logger.error("Failed to get opening Chainlink price")
            return

        logger.info("Window started", price_to_beat=price_to_beat)

        # Resolve slug, token IDs, and condition ID
        slug = get_current_slug()
        market_data = await resolve_market_data(slug)
        if market_data is None:
            logger.error("Failed to resolve market data", slug=slug)
            return

        up_token_id = market_data.up_token_id
        down_token_id = market_data.down_token_id
        condition_id = market_data.condition_id

        logger.info(
            "Market data resolved",
            slug=slug,
            condition_id=condition_id,
            up_token_id=up_token_id,
            down_token_id=down_token_id,
        )

        # Wait until T-30s (30 seconds before window close)
        await sleep_until(30)

        # Evaluate the signal
        trade_decision: Optional[TradeDecision] = await self.strategy.evaluate_window(
            feeds=self.feeds,
            signal_scorer=self.signal_scorer,
            state=self.state,
            up_token_id=up_token_id,
            down_token_id=down_token_id,
        )

        if trade_decision is None:
            logger.info("No trade decision made")
            return

        logger.info("Trade decision made", decision=trade_decision)

        # Place the order
        if self.mode == "dry-run":
            logger.info("Dry-run mode: would place order", decision=trade_decision)
        else:
            success = await build_and_post_order(
                client=self.clob_client,
                token_id=trade_decision.token_id,
                side=trade_decision.side,
                price=trade_decision.price,
                size=trade_decision.size,
            )

            if not success:
                logger.error("Failed to place order")
                return

            logger.info("Order placed successfully")

            # Wait until T-5s, then cancel all open orders as safety net
            await sleep_until(5)
            await self.clob_client.cancel_all()

        # Wait for resolution
        remaining = get_time_remaining()
        await asyncio.sleep(remaining + CONFIG.RESOLUTION_WAIT_SECONDS)

        # Auto-redeem
        if self.mode != "dry-run":
            amount = await redeem_if_resolved(
                client=self.clob_client,
                slug=slug,
                condition_id=condition_id,
                side=trade_decision.side if trade_decision else "",
                entry_price=trade_decision.price if trade_decision else 0.0,
                entry_size=trade_decision.size if trade_decision else 0.0,
            )
            if amount is not None:
                is_win = amount > 0
                self.state.update_after_trade(amount, is_win)
                self.state.current_position = None
                logger.info(
                    "Trade settled",
                    pnl=amount,
                    is_win=is_win,
                    bankroll=self.state.bankroll,
                    win_rate=self.state.get_win_rate(),
                )
            else:
                logger.warning("Redemption not available yet, will retry next cycle")
        else:
            logger.info("Dry-run: skipping redemption")

        logger.info(
            "Window completed",
            bankroll=self.state.bankroll,
            total_trades=self.state.total_trades,
            win_rate=self.state.get_win_rate(),
        )
