"""
Polymarket RTDS WebSocket feed for Chainlink BTC/USD prices.

This module connects to the Polymarket RTDS WebSocket stream,
subscribes to the Chainlink BTC/USD price feed, and maintains
the current price and price_to_beat for the active 5-minute window.
"""

import asyncio
from dataclasses import dataclass
from typing import Optional

import orjson
import picows
from structlog import get_logger

from src.config import CONFIG


logger = get_logger(__name__)


@dataclass(slots=True)
class ChainlinkPrice:
    """Dataclass representing a Chainlink BTC/USD price.

    Attributes:
        price: BTC/USD price.
        timestamp: Unix timestamp in milliseconds.
    """

    price: float
    timestamp: int


class PolymarketRTDS:
    """Polymarket RTDS WebSocket client for Chainlink BTC/USD prices.

    Attributes:
        ws_url: WebSocket URL for Polymarket RTDS.
        current_price: Current Chainlink BTC/USD price.
        price_to_beat: Price at the start of the current 5-minute window.
        reconnect_attempts: Number of reconnection attempts.
        max_reconnect_delay: Maximum delay between reconnection attempts.
    """

    def __init__(self) -> None:
        """Initialize the Polymarket RTDS client."""
        self.ws_url: str = CONFIG.POLYMARKET_RTDS_URL
        self.current_price: Optional[float] = None
        self.price_to_beat: Optional[float] = None
        self.reconnect_attempts: int = 0
        self.max_reconnect_delay: int = 30
        self.ws: Optional[picows.WebSocket] = None

    async def connect(self) -> None:
        """Connect to the Polymarket RTDS WebSocket stream."""
        while True:
            try:
                self.ws = picows.WebSocket(self.ws_url)
                await self.ws.connect()
                logger.info("Connected to Polymarket RTDS WebSocket")
                await self.subscribe()
                await self.listen()
            except Exception as e:
                logger.error("Polymarket RTDS WebSocket error", error=str(e))
                await self.reconnect()

    async def subscribe(self) -> None:
        """Subscribe to the Chainlink BTC/USD price feed."""
        if self.ws is None:
            return

        subscribe_message = orjson.dumps(
            {
                "action": "subscribe",
                "channel": "crypto_prices_chainlink",
                "symbol": "BTC/USD",
            }
        )
        await self.ws.send(subscribe_message)
        logger.info("Subscribed to Chainlink BTC/USD price feed")

    async def listen(self) -> None:
        """Listen for incoming messages from the WebSocket."""
        if self.ws is None:
            return

        while True:
            try:
                message = await self.ws.recv()
                data = orjson.loads(message)
                await self.handle_message(data)
            except Exception as e:
                logger.error("Error parsing Polymarket RTDS message", error=str(e))
                break

    async def handle_message(self, data: dict) -> None:
        """Handle incoming messages from the WebSocket.

        Args:
            data: Raw message data.
        """
        try:
            if data.get("type") == "price_update":
                self.current_price = float(data["price"])
                logger.debug("Chainlink price updated", price=self.current_price)
            elif data.get("type") == "window_start":
                self.price_to_beat = float(data["price"])
                logger.info("New 5-minute window started", price_to_beat=self.price_to_beat)
        except (KeyError, ValueError) as e:
            logger.error("Failed to handle Polymarket RTDS message", error=str(e))

    async def reconnect(self) -> None:
        """Reconnect with exponential backoff."""
        delay = min(2**self.reconnect_attempts, self.max_reconnect_delay)
        logger.info("Reconnecting to Polymarket RTDS WebSocket", delay=delay)
        await asyncio.sleep(delay)
        self.reconnect_attempts += 1

    def get_chainlink_price(self) -> Optional[float]:
        """Get the current Chainlink BTC/USD price.

        Returns:
            Current Chainlink price or None if not available.
        """
        return self.current_price

    def get_price_to_beat(self) -> Optional[float]:
        """Get the price to beat for the current 5-minute window.

        Returns:
            Price to beat or None if not available.
        """
        return self.price_to_beat
