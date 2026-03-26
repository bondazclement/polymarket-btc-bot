"""
Polymarket RTDS WebSocket feed for Chainlink BTC/USD prices.

This module connects to the Polymarket RTDS WebSocket stream,
subscribes to the Chainlink BTC/USD price feed, and maintains
the current price.

MCP-VERIFIED (2026-03-25):
- Subscribe format: {"type": "subscribe", "topic": "crypto_prices_chainlink",
                     "filter": {"symbol": "btc/usd"}}
- Incoming message format: {"topic": "...", "type": "update", "timestamp": ...,
                             "payload": {"symbol": "btc/usd", "value": 45000.5, ...}}
- price_to_beat is NOT set via a RTDS event — it is set by loop.py at T=0
  via set_price_to_beat() after reading get_chainlink_price().
"""

import asyncio
import time
from typing import Optional

import aiohttp
import orjson
from structlog import get_logger

from src.config import CONFIG


logger = get_logger(__name__)


class PolymarketRTDS:
    """Polymarket RTDS WebSocket client for Chainlink BTC/USD prices.

    Attributes:
        ws_url: WebSocket URL for Polymarket RTDS.
        current_price: Current Chainlink BTC/USD price (updated continuously).
        price_to_beat: Price at the start of the current 5-minute window.
                       Set by TradingLoop via set_price_to_beat() at T=0.
        reconnect_attempts: Number of reconnection attempts.
        max_reconnect_delay: Maximum delay between reconnection attempts.
    """

    def __init__(self) -> None:
        """Initialize the Polymarket RTDS client."""
        self.ws_url: str = CONFIG.POLYMARKET_RTDS_URL
        self.current_price: Optional[float] = None
        self.price_to_beat: Optional[float] = None  # Set by TradingLoop via set_price_to_beat()
        self.reconnect_attempts: int = 0
        self.max_reconnect_delay: int = 30
        self.ws: aiohttp.ClientWebSocketResponse | None = None
        self._session: aiohttp.ClientSession | None = None
        self.last_message_ts: float = 0.0

    async def connect(self) -> None:
        """Connect to the Polymarket RTDS WebSocket stream.

        Runs _ping_loop() concurrently with _listen() to send application-level
        PINGs every 5 seconds as required by the RTDS documentation.
        Re-subscribes automatically on every reconnection via _subscribe().
        """
        while True:
            try:
                session = aiohttp.ClientSession()
                self._session = session
                self.ws = await session.ws_connect(self.ws_url)
                logger.info("Connected to Polymarket RTDS WebSocket")
                self.reconnect_attempts = 0
                await self._subscribe()
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
                logger.error("Polymarket RTDS WebSocket error", error=str(e))
            finally:
                if self._session and not self._session.closed:
                    await self._session.close()
                self._session = None
                self.ws = None
            await self._reconnect()

    async def _subscribe(self) -> None:
        """Subscribe to the Chainlink BTC/USD price feed via RTDS.

        Uses the official RTDS subscription format with type/topic/filter.
        """
        if self.ws is None:
            return

        subscribe_message = orjson.dumps(
            {
                "type": "subscribe",
                "topic": "crypto_prices_chainlink",
                "filter": {"symbol": "btc/usd"},
            }
        )
        await self.ws.send_str(subscribe_message.decode())
        logger.info("Subscribed to RTDS Chainlink BTC/USD feed")

    async def _ping_loop(self) -> None:
        """Send application-level PING text frame every 5s to keep connection alive.

        Polymarket RTDS requires a plain-text "PING" every 5 seconds.
        This is distinct from the protocol-level WebSocket ping (RFC 6455).
        The server responds with a plain-text "PONG".
        """
        while True:
            await asyncio.sleep(5)
            if self.ws and not self.ws.closed:
                try:
                    await self.ws.send_str("PING")
                    logger.debug("PING sent to RTDS")
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
                    logger.debug("PONG received from RTDS")
                    self.last_message_ts = time.monotonic()
                    continue
                data = orjson.loads(msg.data)
                logger.debug("Raw WS message received", data_type=data.get("type", "unknown"))
                self._handle_message(data)
                self.last_message_ts = time.monotonic()
            elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                break

    def _handle_message(self, data: dict) -> None:
        """Handle incoming RTDS messages.

        Parses Chainlink price update events (type: "update", topic: "crypto_prices_chainlink").
        The price_to_beat is NOT set here — it is set by loop.py at window T=0
        via set_price_to_beat().

        Args:
            data: Raw RTDS message dict.
        """
        try:
            topic = data.get("topic", "")
            msg_type = data.get("type", "")

            if topic == "crypto_prices_chainlink" and msg_type == "update":
                payload = data.get("payload", {})
                value = payload.get("value")
                if value is not None:
                    self.current_price = float(value)
                    logger.debug("Chainlink price updated", price=self.current_price)

        except (KeyError, ValueError, TypeError) as e:
            logger.error(
                "Failed to handle RTDS message",
                error=str(e),
                data=str(data)[:200],
            )

    async def _reconnect(self) -> None:
        """Reconnect with exponential backoff."""
        delay = min(2**self.reconnect_attempts, self.max_reconnect_delay)
        logger.info("Reconnecting to Polymarket RTDS WebSocket", delay=delay)
        await asyncio.sleep(delay)
        self.reconnect_attempts += 1

    def get_last_message_ts(self) -> float:
        """Get the timestamp of the last successfully parsed message.

        Returns:
            Monotonic timestamp of last message, or 0.0 if none received.
        """
        return self.last_message_ts

    def get_chainlink_price(self) -> Optional[float]:
        """Get the current Chainlink BTC/USD price.

        Returns:
            Current Chainlink price or None if not available.
        """
        return self.current_price

    def set_price_to_beat(self, price: float) -> None:
        """Set the opening price for the current 5-minute window.

        Called by TradingLoop at window T=0 after reading get_chainlink_price().
        This replaces the former 'window_start' event which does not exist in
        the real RTDS API.

        Args:
            price: Chainlink BTC/USD price at window opening.
        """
        self.price_to_beat = price
        logger.info("Price to beat set for new window", price_to_beat=price)

    def get_price_to_beat(self) -> Optional[float]:
        """Get the price to beat for the current 5-minute window.

        Returns:
            Price to beat or None if not available.
        """
        return self.price_to_beat
