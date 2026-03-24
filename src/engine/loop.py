"""
Trading loop module for the Polymarket BTC UpDown 5m trading bot.

This module provides the main trading loop that runs indefinitely,
executing one iteration per 5-minute trading window.
"""

import asyncio
from typing import Optional

from structlog import get_logger

from src.config import CONFIG
from src.engine.clock import get_window_start, sleep_until
from src.engine.state import BotState
from src.execution.clob_client import PolymarketClient
from src.execution.order_builder import build_order
from src.execution.redeemer import redeem_if_resolved
from src.execution.slug_resolver import get_current_slug, resolve_token_ids
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
        """Run the main trading loop indefinitely.

        This method executes one iteration per 5-minute trading window,
        performing the following steps:
        1. Wait for the start of the window (T=0).
        2. Record the opening Chainlink price.
        3. Resolve the slug and token IDs.
        4. Wait until T-30 seconds.
        5. Evaluate the signal using TakerSelectiveStrategy.
        6. If a trade is decided, place the order.
        7. Monitor execution until T-5 seconds, cancel if not filled.
        8. Wait for resolution (T+10 seconds).
        9. Auto-redeem.
        10. Log the result and update the state.
        """
        await self.feeds.start_all()

        while True:
            try:
                await self._run_window()
            except Exception as e:
                logger.error("Error in trading window", error=str(e))
                await asyncio.sleep(5)

    async def _run_window(self) -> None:
        """Run a single trading window iteration."""
        # Wait for the start of the window
        window_start = get_window_start()
        logger.info("Waiting for window start", window_start=window_start)
        await sleep_until(300)

        # Record the opening Chainlink price
        price_to_beat = self.feeds.polymarket_rtds_feed.get_price_to_beat()
        if price_to_beat is None:
            logger.error("Failed to get opening Chainlink price")
            return

        logger.info("Window started", price_to_beat=price_to_beat)

        # Resolve the slug and token IDs
        slug = get_current_slug()
        up_token_id, down_token_id = await resolve_token_ids(slug)
        if not up_token_id or not down_token_id:
            logger.error("Failed to resolve token IDs")
            return

        logger.info("Token IDs resolved", up_token_id=up_token_id, down_token_id=down_token_id)

        # Wait until T-30 seconds
        await sleep_until(30)

        # Evaluate the signal
        trade_decision: Optional[TradeDecision] = await self.strategy.evaluate_window(
            feeds=self.feeds, signal_scorer=self.signal_scorer, state=self.state
        )

        if trade_decision is None:
            logger.info("No trade decision made")
            return

        logger.info("Trade decision made", decision=trade_decision)

        # Place the order
        if self.mode == "dry-run":
            logger.info("Dry-run mode: would place order", decision=trade_decision)
        else:
            order = await build_order(
                client=self.clob_client.client,
                token_id=trade_decision.token_id,
                side=trade_decision.side,
                price=trade_decision.price,
                size=trade_decision.size,
            )

            if order is None:
                logger.error("Failed to build order")
                return

            placed = await self.clob_client.place_order(order)
            if not placed:
                logger.error("Failed to place order")
                return

            logger.info("Order placed successfully", order_id=order.order_id)

            # Monitor execution until T-5 seconds
            await sleep_until(5)

            # Cancel the order if not filled
            if not order.is_filled:
                cancelled = await self.clob_client.cancel_order(order.order_id)
                if cancelled:
                    logger.info("Order cancelled successfully", order_id=order.order_id)
                else:
                    logger.error("Failed to cancel order", order_id=order.order_id)

        # Wait for resolution (T+10 seconds)
        await asyncio.sleep(10)

        # Auto-redeem
        if self.state.current_position:
            amount = await redeem_if_resolved(self.clob_client.client, self.state.current_position)
            if amount is not None:
                logger.info("Tokens redeemed successfully", amount=amount)
                self.state.update_after_trade(amount, True)
            else:
                logger.error("Failed to redeem tokens")
                self.state.update_after_trade(0.0, False)

        # Log the result and update the state
        logger.info("Window completed", state=self.state)
