"""
Trading loop module for the Polymarket BTC UpDown 5m trading bot.

This module provides the main trading loop that runs indefinitely,
executing one iteration per 5-minute trading window.

Séquence T=0 :
1. Capturer prix Chainlink via get_chainlink_price()
2. Appeler set_price_to_beat() sur le feed RTDS
3. Résoudre le slug + market data (condition_id, up_token_id, down_token_id)
4. Appeler subscribe_assets() sur le feed CLOB WS avec les vrais token_ids

Note : PolymarketClient n'est instancié qu'en mode non-dry-run.
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
        clob_client: PolymarketClient for interacting with the CLOB (None in dry-run).
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
        # Guard dry-run : ne pas instancier PolymarketClient avec des clés vides
        # py-clob-client peut lever une exception à l'init si la clé privée est invalide
        self.clob_client: Optional[PolymarketClient] = (
            PolymarketClient() if mode != "dry-run" else None
        )
        self.mode = mode

    async def run(self) -> None:
        """Run the main trading loop indefinitely."""
        await self.feeds.start_all()

        while True:
            try:
                await self._run_window()
            except Exception as e:
                remaining = get_time_remaining()
                wait_seconds = max(remaining, 0.0) + 1.0
                logger.error(
                    "Error in trading window",
                    error=str(e),
                    wait_seconds=wait_seconds,
                )
                await asyncio.sleep(wait_seconds)

    async def _run_window(self) -> None:
        """Run a single trading window iteration.

        Séquence :
        - Attendre le début de la prochaine fenêtre
        - Capturer prix Chainlink (price_to_beat) à T=0
        - Résoudre le slug + token_ids
        - Subscribe CLOB WS sur ces token_ids
        - À T=270s : évaluer le signal
        - À T=285s : placer l'ordre (si mode != dry-run)
        - À T=295s : cancel safety net
        - Post-fenêtre : redeem + P&L
        """
        remaining = get_time_remaining()
        window_start = get_window_start()

        # Si trop peu de temps dans la fenêtre courante, attendre la prochaine
        if remaining < 30:
            wait_seconds = remaining + 1
            logger.info(
                "Window nearly over, waiting for next",
                remaining=remaining,
                wait_seconds=wait_seconds,
            )
            await asyncio.sleep(wait_seconds)
            remaining = get_time_remaining()
            window_start = get_window_start()

        logger.info(
            "New window started",
            window_start=window_start,
            time_remaining=remaining,
        )

        # ─── T=0 : Capturer le prix Chainlink d'ouverture ──────────────────────
        opening_price = self._get_opening_chainlink_price()
        if opening_price is None:
            logger.error(
                "Failed to get opening Chainlink price — RTDS not connected or no data yet"
            )
            await asyncio.sleep(10)
            return

        # Stocker le prix d'ouverture dans le feed (pour taker_selective.py)
        self.feeds.polymarket_rtds_feed.set_price_to_beat(opening_price)
        logger.info("Window opened", price_to_beat=opening_price)

        # ─── T=0 : Résoudre le slug et les token_ids ───────────────────────────
        # Utiliser window_start pour cohérence (évite les décalages si on est à T+epsilon)
        # Fallback sur get_current_slug() sans argument si la signature ne supporte pas timestamp
        try:
            slug = get_current_slug(timestamp=window_start)
        except TypeError:
            slug = get_current_slug()

        try:
            market_data = await resolve_market_data(slug)
        except Exception as e:
            logger.error("Failed to resolve market data", slug=slug, error=str(e))
            await asyncio.sleep(10)
            return

        # resolve_market_data retourne Optional[MarketData] (dataclass, pas dict)
        if market_data is None:
            logger.error("Market data is None — market not found for slug", slug=slug)
            await asyncio.sleep(10)
            return

        # Accès par attributs (MarketData est une dataclass, PAS un dict)
        condition_id: str = market_data.condition_id
        up_token_id: str = market_data.up_token_id
        down_token_id: str = market_data.down_token_id

        logger.info(
            "Market data resolved",
            slug=slug,
            condition_id=condition_id[:20] + "...",
            up_token_id=up_token_id[:20] + "...",
            down_token_id=down_token_id[:20] + "...",
        )

        # ─── T=0 : Subscribe CLOB WS sur les token_ids résolus ─────────────────
        # CRITIQUE : appelé APRÈS resolve_market_data, pas à la connexion
        # subscribe_assets() stocke les IDs pour re-subscribe automatique après reconnexion
        await self.feeds.polymarket_clob_feed.subscribe_assets(
            [up_token_id, down_token_id]
        )
        logger.info(
            "Subscribed to CLOB assets",
            up_token_id=up_token_id,
            down_token_id=down_token_id,
        )

        # ─── T=0 → T=270 : Attendre l'évaluation ──────────────────────────────
        await sleep_until(30)  # Attendre jusqu'à T=270 (30s restantes)

        remaining = get_time_remaining()
        if remaining <= 0:
            logger.warning("Window expired before evaluation", remaining=remaining)
            return

        # ─── T=270 : Évaluer le signal ─────────────────────────────────────────
        trade_decision: Optional[TradeDecision] = await self.strategy.evaluate_window(
            feeds=self.feeds,
            signal_scorer=self.signal_scorer,
            state=self.state,
            up_token_id=up_token_id,
            down_token_id=down_token_id,
        )

        if trade_decision is None:
            logger.info("No trade decision — window skipped")
            return

        logger.info(
            "Trade decision made",
            side=trade_decision.side,
            token_id=trade_decision.token_id[:20] + "...",
            price=trade_decision.price,
            size=trade_decision.size,
            confidence=trade_decision.confidence,
            mode=self.mode,
        )

        # ─── T=285 : Placer l'ordre (hors dry-run) ─────────────────────────────
        await sleep_until(15)  # Attendre jusqu'à T=285 (15s restantes)

        order_id: Optional[str] = None
        if self.mode != "dry-run" and self.clob_client is not None:
            try:
                order_id = await build_and_post_order(
                    client=self.clob_client,
                    token_id=trade_decision.token_id,
                    side=trade_decision.side,
                    price=trade_decision.price,
                    size=trade_decision.size,
                )
                logger.info("Order placed", order_id=order_id)
            except Exception as e:
                logger.error("Failed to place order", error=str(e))
                return
        else:
            logger.info(
                "Dry-run mode — would place order",
                side=trade_decision.side,
                price=trade_decision.price,
                size=trade_decision.size,
            )

        # ─── T=295 : Cancel safety net ─────────────────────────────────────────
        await sleep_until(5)  # Attendre jusqu'à T=295 (5s restantes)

        if self.mode != "dry-run" and self.clob_client is not None and order_id:
            try:
                await asyncio.to_thread(self.clob_client.client.cancel_all)
                logger.info("Cancel all orders sent (safety net)")
            except Exception as e:
                logger.warning("Failed to cancel orders", error=str(e))

        # ─── T=300+ : Attendre résolution et redeem ────────────────────────────
        # Laisser la fenêtre se fermer complètement
        remaining = get_time_remaining()
        if remaining > 0:
            await asyncio.sleep(remaining + CONFIG.RESOLUTION_WAIT_SECONDS)
        else:
            await asyncio.sleep(CONFIG.RESOLUTION_WAIT_SECONDS)

        logger.info("Window closed, waiting for resolution")

        if self.mode != "dry-run" and self.clob_client is not None and order_id:
            try:
                pnl, is_win = await redeem_if_resolved(
                    client=self.clob_client,
                    slug=slug,
                    condition_id=condition_id,
                    side=trade_decision.side,
                    entry_price=trade_decision.price,
                    entry_size=trade_decision.size,
                )
                self.state.update_after_trade(pnl=pnl, is_win=is_win)
                logger.info(
                    "Trade result",
                    pnl=pnl,
                    is_win=is_win,
                    bankroll=self.state.bankroll,
                    win_rate=self.state.win_rate,
                )
            except Exception as e:
                logger.error("Failed to redeem", error=str(e))

    def _get_opening_chainlink_price(self) -> Optional[float]:
        """Return RTDS Chainlink price with compatibility fallbacks.

        Returns:
            Opening Chainlink price if available, else None.
        """
        rtds_feed = self.feeds.polymarket_rtds_feed

        get_chainlink_price = getattr(rtds_feed, "get_chainlink_price", None)
        if callable(get_chainlink_price):
            price = get_chainlink_price()
            if isinstance(price, (int, float)):
                return float(price)

        get_current_price = getattr(rtds_feed, "get_current_price", None)
        if callable(get_current_price):
            price = get_current_price()
            if isinstance(price, (int, float)):
                return float(price)

        raw_price = getattr(rtds_feed, "current_price", None)
        if isinstance(raw_price, (int, float)):
            return float(raw_price)

        return None
