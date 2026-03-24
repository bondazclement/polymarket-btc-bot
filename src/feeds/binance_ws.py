"""
Binance WebSocket feed for BTC/USDT aggregated trades.

This module connects to the Binance WebSocket stream for BTC/USDT trades,
parses incoming messages, and maintains a buffer of recent ticks.
"""

import asyncio
from collections import deque
from dataclasses import dataclass
from typing import Deque

import orjson
import picows
from structlog import get_logger

from src.config import CONFIG


logger = get_logger(__name__)


@dataclass(slots=True)
class Tick:
    """Dataclass representing a single trade tick.

    Attributes:
        price: Trade price in USDT.
        quantity: Trade quantity in BTC.
        timestamp: Unix timestamp in milliseconds.
        is_buyer_maker: Whether the buyer was the maker.
    """

    price: float
    quantity: float
    timestamp: int
    is_buyer_maker: bool


class BinanceWebSocket:
    """Binance WebSocket client for BTC/USDT aggregated trades.

    Attributes:
        ws_url: WebSocket URL for Binance BTC/USDT trades.
        tick_buffer: Buffer of recent ticks (max 600).
        reconnect_attempts: Number of reconnection attempts.
        max_reconnect_delay: Maximum delay between reconnection attempts.
    """

    def __init__(self) -> None:
        """Initialize the Binance WebSocket client."""
        self.ws_url: str = CONFIG.BINANCE_WS_URL
        self.tick_buffer: Deque[Tick] = deque(maxlen=600)
        self.reconnect_attempts: int = 0
        self.max_reconnect_delay: int = 30
        self.ws: picows.WebSocket | None = None

    async def connect(self) -> None:
        """Connect to the Binance WebSocket stream."""
        while True:
            try:
                self.ws = picows.WebSocket(self.ws_url)
                await self.ws.connect()
                logger.info("Connected to Binance WebSocket")
                await self.listen()
            except Exception as e:
                logger.error("Binance WebSocket error", error=str(e))
                await self.reconnect()

    async def listen(self) -> None:
        """Listen for incoming messages from the WebSocket."""
        if self.ws is None:
            return

        while True:
            try:
                message = await self.ws.recv()
                data = orjson.loads(message)
                tick = self.parse_tick(data)
                if tick:
                    self.tick_buffer.append(tick)
            except Exception as e:
                logger.error("Error parsing Binance message", error=str(e))
                break

    def parse_tick(self, data: dict) -> Tick | None:
        """Parse a Binance trade message into a Tick object.

        Args:
            data: Raw Binance trade message.

        Returns:
            Parsed Tick object or None if parsing fails.
        """
        try:
            return Tick(
                price=float(data["p"]),
                quantity=float(data["q"]),
                timestamp=int(data["T"]),
                is_buyer_maker=bool(data["m"]),
            )
        except (KeyError, ValueError) as e:
            logger.error("Failed to parse Binance tick", error=str(e))
            return None

    async def reconnect(self) -> None:
        """Reconnect with exponential backoff."""
        delay = min(2**self.reconnect_attempts, self.max_reconnect_delay)
        logger.info("Reconnecting to Binance WebSocket", delay=delay)
        await asyncio.sleep(delay)
        self.reconnect_attempts += 1

    def get_latest_price(self) -> float:
        """Get the latest trade price.

        Returns:
            Latest trade price or 0.0 if no trades are available.
        """
        if not self.tick_buffer:
            return 0.0
        return self.tick_buffer[-1].price

    def get_price_buffer(self) -> Deque[Tick]:
        """Get the buffer of recent ticks.

        Returns:
            Deque of recent Tick objects.
        """
        return self.tick_buffer
