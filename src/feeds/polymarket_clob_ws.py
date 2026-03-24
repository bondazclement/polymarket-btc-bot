"""
Polymarket CLOB WebSocket feed for order book data.

This module connects to the Polymarket CLOB WebSocket stream,
subscribes to the order book for the active market, and maintains
the best bid and ask prices for each token.
"""

import asyncio
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
        reconnect_attempts: Number of reconnection attempts.
        max_reconnect_delay: Maximum delay between reconnection attempts.
    """

    def __init__(self) -> None:
        """Initialize the Polymarket CLOB WebSocket client."""
        self.ws_url: str = f"{CONFIG.POLYMARKET_CLOB_URL}/ws/market"
        self.order_books: Dict[str, Dict[str, List[OrderBookLevel]]] = {}
        self.reconnect_attempts: int = 0
        self.max_reconnect_delay: int = 30
        self.ws: aiohttp.ClientWebSocketResponse | None = None
        self._session: aiohttp.ClientSession | None = None

    async def connect(self) -> None:
        """Connect to the Polymarket CLOB WebSocket stream."""
        while True:
            try:
                session = aiohttp.ClientSession()
                self._session = session
                self.ws = await session.ws_connect(self.ws_url)
                logger.info("Connected to Polymarket CLOB WebSocket")
                self.reconnect_attempts = 0
                await self._subscribe()
                await self._listen()
            except Exception as e:
                logger.error("Polymarket CLOB WebSocket error", error=str(e))
                if self._session:
                    await self._session.close()
                    self._session = None
                await self._reconnect()

    async def _subscribe(self) -> None:
        """Subscribe to the order book for the active market."""
        if self.ws is None:
            return

        subscribe_message = orjson.dumps(
            {
                "action": "subscribe",
                "channel": "order_book",
                "market": "btc-updown-5m",
            }
        )
        await self.ws.send_str(subscribe_message.decode())
        logger.info("Subscribed to Polymarket CLOB order book")

    async def _listen(self) -> None:
        """Listen for incoming messages from the WebSocket."""
        if self.ws is None:
            return

        async for msg in self.ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                data = orjson.loads(msg.data)
                self._handle_message(data)
            elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                break

    def _handle_message(self, data: dict) -> None:
        """Handle incoming messages from the WebSocket.

        Args:
            data: Raw message data.
        """
        try:
            if data.get("type") == "order_book_update":
                token_id = data["token_id"]
                if token_id not in self.order_books:
                    self.order_books[token_id] = {"bids": [], "asks": []}

                bids = data.get("bids", [])
                asks = data.get("asks", [])

                self.order_books[token_id]["bids"] = [
                    OrderBookLevel(price=float(bid[0]), size=float(bid[1])) for bid in bids
                ]
                self.order_books[token_id]["asks"] = [
                    OrderBookLevel(price=float(ask[0]), size=float(ask[1])) for ask in asks
                ]

                logger.debug("Order book updated", token_id=token_id)
        except (KeyError, ValueError) as e:
            logger.error("Failed to handle Polymarket CLOB message", error=str(e))

    async def _reconnect(self) -> None:
        """Reconnect with exponential backoff."""
        delay = min(2**self.reconnect_attempts, self.max_reconnect_delay)
        logger.info("Reconnecting to Polymarket CLOB WebSocket", delay=delay)
        await asyncio.sleep(delay)
        self.reconnect_attempts += 1

    def get_best_ask(self, token_id: str) -> Optional[float]:
        """Get the best ask price for a token.

        Args:
            token_id: Token ID.

        Returns:
            Best ask price or None if not available.
        """
        if token_id not in self.order_books or not self.order_books[token_id]["asks"]:
            return None
        return self.order_books[token_id]["asks"][0].price

    def get_best_bid(self, token_id: str) -> Optional[float]:
        """Get the best bid price for a token.

        Args:
            token_id: Token ID.

        Returns:
            Best bid price or None if not available.
        """
        if token_id not in self.order_books or not self.order_books[token_id]["bids"]:
            return None
        return self.order_books[token_id]["bids"][0].price
