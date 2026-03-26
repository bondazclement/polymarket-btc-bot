"""
Polymarket CLOB WebSocket feed for order book data.

This module connects to the Polymarket CLOB WebSocket market channel,
subscribes to order book updates for the active BTC 5m market tokens,
and maintains a local cache of best bid/ask prices.

Formats validés via MCP + doc officielle Polymarket (26 mars 2026) :
- Subscribe  : {"assets_ids": ["<up_id>", "<down_id>"], "type": "market",
                "custom_feature_enabled": true}
- Events     : event_type (pas "type"), asset_id (pas "token_id")
  - "book"         : snapshot complet, bids/asks = [{price, size}, ...]
  - "best_bid_ask" : top of book, best_bid/best_ask = "0.52" (string)
- Keepalive  : heartbeat=20.0 dans aiohttp suffit pour le CLOB WS (RFC 6455)
"""

import asyncio
import time
from dataclasses import dataclass
from typing import Dict, List, Optional

import aiohttp
import orjson
from structlog import get_logger

from src.config import CONFIG


logger = get_logger(__name__)


@dataclass(slots=True)
class OrderBookLevel:
    """A single price level in the order book.

    Attributes:
        price: Price at this level.
        size: Size available at this level.
    """

    price: float
    size: float


class PolymarketCLOBWebSocket:
    """Polymarket CLOB WebSocket client for order book data.

    Subscribes to the market channel for specific token IDs (resolved via Gamma API).
    subscribe_assets() must be called from loop.py after resolve_market_data()
    returns the up/down token IDs.

    Maintains two caches:
    - order_books: full book snapshots from "book" events
    - best_prices: top of book from "best_bid_ask" events (preferred, faster)

    Attributes:
        ws_url: WebSocket URL for Polymarket CLOB market channel.
        order_books: Per-token full order book cache.
        best_prices: Per-token best bid/ask cache (fast path).
        last_message_ts: Monotonic timestamp of last received message.
    """

    def __init__(self) -> None:
        """Initialize the Polymarket CLOB WebSocket client."""
        self.ws_url: str = CONFIG.POLYMARKET_CLOB_WS_URL
        self.order_books: Dict[str, Dict[str, List[OrderBookLevel]]] = {}
        self.best_prices: Dict[str, Dict[str, float]] = {}
        # Format : {"<token_id>": {"best_bid": 0.48, "best_ask": 0.52}}
        self.reconnect_attempts: int = 0
        self.max_reconnect_delay: int = 30
        self.ws: aiohttp.ClientWebSocketResponse | None = None
        self._session: aiohttp.ClientSession | None = None
        self.last_message_ts: float = 0.0
        # Stockage des token_ids pour re-subscribe automatique après reconnexion
        self._subscribed_token_ids: List[str] = []

    async def connect(self) -> None:
        """Connect to the Polymarket CLOB WebSocket market channel.

        Re-subscribes automatically after reconnection if token_ids are known.
        """
        while True:
            try:
                session = aiohttp.ClientSession()
                self._session = session
                # heartbeat=20.0 : RFC 6455 pings gérés par aiohttp (suffit pour CLOB WS)
                self.ws = await session.ws_connect(self.ws_url, heartbeat=20.0)
                logger.info("Connected to Polymarket CLOB WebSocket")
                self.reconnect_attempts = 0

                # Re-subscribe automatiquement si des token_ids sont connus
                # (cas reconnexion mid-window)
                if self._subscribed_token_ids:
                    await self._send_subscribe(self._subscribed_token_ids)
                    logger.info(
                        "Re-subscribed to CLOB assets after reconnection",
                        token_ids=self._subscribed_token_ids,
                    )

                await self._listen()
            except Exception as e:
                logger.error("Polymarket CLOB WebSocket error", error=str(e))
            finally:
                if self._session and not self._session.closed:
                    await self._session.close()
                self._session = None
                self.ws = None
            await self._reconnect()

    async def subscribe_assets(self, token_ids: List[str]) -> None:
        """Subscribe to order book updates for the given token IDs.

        Must be called from loop.py after resolve_market_data() returns token IDs.
        Idempotent: re-subscribing with new token IDs is safe.
        Stores token_ids for automatic re-subscription after reconnection.

        Args:
            token_ids: List of CLOB token IDs (e.g. [up_token_id, down_token_id]).
        """
        if not token_ids:
            logger.warning("subscribe_assets called with empty token_ids list")
            return

        # Stocker pour re-subscribe automatique après reconnexion
        self._subscribed_token_ids = list(token_ids)

        if self.ws is None or self.ws.closed:
            logger.warning(
                "Cannot subscribe now: CLOB WS not connected — will auto-subscribe on reconnect",
                token_ids=token_ids,
            )
            return

        await self._send_subscribe(token_ids)

    async def _send_subscribe(self, token_ids: List[str]) -> None:
        """Send the subscribe message to the CLOB WebSocket.

        Format officiel validé :
        {"assets_ids": [...], "type": "market", "custom_feature_enabled": true}

        Args:
            token_ids: List of CLOB token IDs to subscribe to.
        """
        if self.ws is None or self.ws.closed:
            return

        payload = orjson.dumps({
            "assets_ids": token_ids,
            "type": "market",
            "custom_feature_enabled": True,
        })
        await self.ws.send_str(payload.decode())
        logger.info("Subscribed to CLOB assets", token_ids=token_ids)

    async def _listen(self) -> None:
        """Listen for incoming messages from the CLOB WebSocket."""
        if self.ws is None:
            return

        async for msg in self.ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                try:
                    data: dict | list = orjson.loads(msg.data)
                    if isinstance(data, list):
                        logger.debug(
                            "Raw WS message received",
                            msg_count=len(data),
                        )
                    else:
                        logger.debug(
                            "Raw WS message received",
                            event_type=data.get("event_type", "unknown"),
                        )
                    self._handle_message(data)
                    self.last_message_ts = time.monotonic()
                except Exception as e:
                    logger.error("Failed to parse CLOB WS message", error=str(e))
            elif msg.type == aiohttp.WSMsgType.PONG:
                # RFC 6455 pong — connection vivante
                self.last_message_ts = time.monotonic()
            elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                break

    def _handle_message(self, data: dict | list) -> None:
        """Handle incoming messages from the CLOB WebSocket.

        Supports both list-wrapped and single-dict messages.
        Handles event_type: 'book' (full snapshot) and 'best_bid_ask' (top of book).

        Champs validés :
        - Discriminant : "event_type" (PAS "type")
        - Identifiant token : "asset_id" (PAS "token_id")
        - bids/asks : [{price: "0.48", size: "30"}, ...] (objets, PAS tuples)

        Args:
            data: Raw parsed message (dict or list of dicts).
        """
        messages = data if isinstance(data, list) else [data]
        for msg in messages:
            event_type = ""
            token_id = ""
            try:
                event_type = msg.get("event_type", "")
                token_id = msg.get("asset_id", "")

                if not token_id:
                    continue

                if event_type == "book":
                    # Snapshot complet du book — remplacer le cache existant
                    if token_id not in self.order_books:
                        self.order_books[token_id] = {"bids": [], "asks": []}
                    self.order_books[token_id]["bids"] = [
                        OrderBookLevel(price=float(b["price"]), size=float(b["size"]))
                        for b in msg.get("bids", [])
                    ]
                    self.order_books[token_id]["asks"] = [
                        OrderBookLevel(price=float(a["price"]), size=float(a["size"]))
                        for a in msg.get("asks", [])
                    ]
                    logger.debug(
                        "Order book snapshot received",
                        token_id=token_id,
                        n_bids=len(self.order_books[token_id]["bids"]),
                        n_asks=len(self.order_books[token_id]["asks"]),
                    )

                elif event_type == "best_bid_ask":
                    # Top of book — fast path pour la stratégie taker
                    # nécessite custom_feature_enabled: true dans le subscribe
                    self.best_prices[token_id] = {
                        "best_bid": float(msg["best_bid"]),
                        "best_ask": float(msg["best_ask"]),
                    }
                    logger.debug(
                        "Best bid/ask updated",
                        token_id=token_id,
                        best_bid=self.best_prices[token_id]["best_bid"],
                        best_ask=self.best_prices[token_id]["best_ask"],
                    )

            except (KeyError, ValueError, TypeError) as e:
                logger.error(
                    "Failed to handle CLOB message",
                    event_type=event_type,
                    token_id=token_id,
                    error=str(e),
                )

    def get_best_ask(self, token_id: str) -> Optional[float]:
        """Get the best ask price for a token.

        Reads from best_prices cache first (populated by best_bid_ask events),
        falls back to order_books (populated by book events).

        Args:
            token_id: CLOB token ID.

        Returns:
            Best ask price as float, or None if no data available.
        """
        # Fast path : cache best_bid_ask (mis à jour à chaque tick)
        if token_id in self.best_prices:
            return self.best_prices[token_id]["best_ask"]
        # Fallback : snapshot complet
        if token_id in self.order_books and self.order_books[token_id]["asks"]:
            return self.order_books[token_id]["asks"][0].price
        return None

    def get_best_bid(self, token_id: str) -> Optional[float]:
        """Get the best bid price for a token.

        Args:
            token_id: CLOB token ID.

        Returns:
            Best bid price as float, or None if no data available.
        """
        if token_id in self.best_prices:
            return self.best_prices[token_id]["best_bid"]
        if token_id in self.order_books and self.order_books[token_id]["bids"]:
            return self.order_books[token_id]["bids"][0].price
        return None

    def get_order_book(self, token_id: str) -> Optional[Dict[str, List[OrderBookLevel]]]:
        """Get the full order book for a token.

        Args:
            token_id: CLOB token ID.

        Returns:
            Dict with 'bids' and 'asks' lists, or None if no data available.
        """
        return self.order_books.get(token_id)

    async def _reconnect(self) -> None:
        """Reconnect with exponential backoff."""
        delay = min(2 ** self.reconnect_attempts, self.max_reconnect_delay)
        logger.info("Reconnecting to Polymarket CLOB WebSocket", delay=delay)
        await asyncio.sleep(delay)
        self.reconnect_attempts += 1

    def get_last_message_ts(self) -> float:
        """Get the timestamp of the last successfully parsed message.

        Returns:
            Monotonic timestamp of last message, or 0.0 if none received.
        """
        return self.last_message_ts