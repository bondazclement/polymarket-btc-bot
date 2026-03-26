"""
Polymarket CLOB WebSocket feed for order book data.

This module connects to the Polymarket CLOB WebSocket stream,
subscribes to the order book for the active market, and maintains
the best bid and ask prices for each token.

MCP-VERIFIED (2026-03-25):
- Subscribe format: {"type": "market", "assets_ids": [...], "custom_feature_enabled": true}
- Messages use event_type field (not "type"), asset_id for token identifier
- bids/asks in "book" events are objects: [{"price": "string", "size": "string"}]
- "best_bid_ask" event requires custom_feature_enabled: true
- Messages may arrive as a list of dicts
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
    """Dataclass representing a single level in the order book.

    Attributes:
        price: Price of the order.
        size: Size of the order.
    """

    price: float
    size: float


class PolymarketCLOBWebSocket:
    """Polymarket CLOB WebSocket client for order book data.

    Attributes:
        ws_url: WebSocket URL for Polymarket CLOB.
        order_books: Dictionary of order books by token ID.
        best_prices: Cache of best bid/ask per token ID (from best_bid_ask events).
        reconnect_attempts: Number of reconnection attempts.
        max_reconnect_delay: Maximum delay between reconnection attempts.
    """

    def __init__(self) -> None:
        """Initialize the Polymarket CLOB WebSocket client."""
        self.ws_url: str = CONFIG.POLYMARKET_CLOB_WS_URL
        self.order_books: Dict[str, Dict[str, List[OrderBookLevel]]] = {}
        self.best_prices: Dict[str, Dict[str, float]] = {}
        # Format: {"<token_id>": {"best_bid": 0.48, "best_ask": 0.52}}
        self.reconnect_attempts: int = 0
        self.max_reconnect_delay: int = 30
        self.ws: aiohttp.ClientWebSocketResponse | None = None
        self._session: aiohttp.ClientSession | None = None
        self.last_message_ts: float = 0.0
        self._subscribed_token_ids: list[str] = []

    async def connect(self) -> None:
        """Connect to the Polymarket CLOB WebSocket stream.

        Does NOT subscribe on first connect — subscribe_assets() must be called
        from loop.py after resolve_market_data() returns token IDs.
        On reconnection, automatically re-subscribes if token IDs were previously set.
        Runs _ping_loop() concurrently with _listen() to send application-level PINGs.
        """
        while True:
            try:
                session = aiohttp.ClientSession()
                self._session = session
                self.ws = await session.ws_connect(self.ws_url)
                logger.info("Connected to Polymarket CLOB WebSocket")
                self.reconnect_attempts = 0
                # Re-subscribe on reconnection if we already had token IDs
                if self._subscribed_token_ids:
                    await self.subscribe_assets(self._subscribed_token_ids)
                    logger.info(
                        "Re-subscribed after reconnection",
                        token_ids=self._subscribed_token_ids,
                    )
                ping_task = asyncio.create_task(self._ping_loop())
                try:
                    await self._listen()
                finally:
                    ping_task.cancel()
                    try:
                        await ping_task
                    except asyncio.CancelledError:
                        pass
            except Exception as e:
                logger.error("Polymarket CLOB WebSocket error", error=str(e))
            finally:
                if self._session and not self._session.closed:
                    await self._session.close()
                self._session = None
                self.ws = None
            await self._reconnect()

    async def subscribe_assets(self, token_ids: list[str]) -> None:
        """Subscribe to order book updates for the given token IDs.

        Must be called from loop.py after resolve_market_data() returns token IDs.
        Stores token_ids so they can be re-used automatically after reconnection.
        Idempotent: re-subscribing with new token IDs is safe.

        Args:
            token_ids: List of CLOB token IDs to subscribe to (e.g. [up_id, down_id]).
        """
        if not token_ids:
            logger.warning("subscribe_assets called with empty token_ids list")
            return
        self._subscribed_token_ids = token_ids
        if self.ws is None or self.ws.closed:
            logger.warning(
                "Cannot subscribe: CLOB WS not connected yet", token_ids=token_ids
            )
            return

        payload = orjson.dumps(
            {
                "assets_ids": token_ids,
                "type": "market",
                "custom_feature_enabled": True,
            }
        )
        await self.ws.send_str(payload.decode())
        logger.info("Subscribed to CLOB assets", token_ids=token_ids)

    async def _ping_loop(self) -> None:
        """Send application-level PING text frame every 10s to keep connection alive.

        Polymarket CLOB WS requires a plain-text "PING" every 10 seconds.
        This is distinct from the protocol-level WebSocket ping (RFC 6455).
        The server responds with a plain-text "PONG".
        """
        while True:
            await asyncio.sleep(10)
            if self.ws and not self.ws.closed:
                try:
                    await self.ws.send_str("PING")
                    logger.debug("PING sent to CLOB WS")
                except Exception:
                    break

    async def _listen(self) -> None:
        """Listen for incoming messages from the WebSocket."""
        if self.ws is None:
            return

        async for msg in self.ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                # Handle application-level PONG response (plain text, not JSON)
                if msg.data == "PONG":
                    logger.debug("PONG received from CLOB WS")
                    self.last_message_ts = time.monotonic()
                    continue
                data: dict | list = orjson.loads(msg.data)
                if isinstance(data, list):
                    logger.debug("Raw WS message received", msg_count=len(data))
                else:
                    logger.debug(
                        "Raw WS message received",
                        event_type=data.get("event_type", "unknown"),
                    )
                self._handle_message(data)
                self.last_message_ts = time.monotonic()
            elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                break

    def _handle_message(self, data: dict | list) -> None:
        """Handle incoming messages from the CLOB WebSocket.

        Supports both list-wrapped and single-dict messages.
        Handles event_type: 'book' (full snapshot) and 'best_bid_ask' (top of book).

        Args:
            data: Raw parsed message (dict or list of dicts).
        """
        messages = data if isinstance(data, list) else [data]
        for msg in messages:
            try:
                event_type = msg.get("event_type", "")
                token_id = msg.get("asset_id", "")

                if not token_id:
                    continue

                if event_type == "book":
                    # Full order book snapshot
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
                    # Top of book update — fast path for taker strategy
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
                    event_type=msg.get("event_type", "unknown"),
                    token_id=msg.get("asset_id", "unknown"),
                    error=str(e),
                )

    async def _reconnect(self) -> None:
        """Reconnect with exponential backoff."""
        delay = min(2**self.reconnect_attempts, self.max_reconnect_delay)
        logger.info("Reconnecting to Polymarket CLOB WebSocket", delay=delay)
        await asyncio.sleep(delay)
        self.reconnect_attempts += 1

    def get_last_message_ts(self) -> float:
        """Get the timestamp of the last successfully parsed message.

        Returns:
            Monotonic timestamp of last message, or 0.0 if none received.
        """
        return self.last_message_ts

    def get_best_ask(self, token_id: str) -> Optional[float]:
        """Get the best ask price for a token.

        Reads from best_prices cache first (populated by best_bid_ask events),
        falls back to order_books (populated by book events).

        Args:
            token_id: CLOB token ID.

        Returns:
            Best ask price as float, or None if no data available.
        """
        # Fast path: best_bid_ask event cache
        if token_id in self.best_prices:
            return self.best_prices[token_id]["best_ask"]
        # Fallback: full book
        if token_id in self.order_books and self.order_books[token_id]["asks"]:
            return self.order_books[token_id]["asks"][0].price
        return None

    def get_best_bid(self, token_id: str) -> Optional[float]:
        """Get the best bid price for a token.

        Reads from best_prices cache first (populated by best_bid_ask events),
        falls back to order_books (populated by book events).

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
