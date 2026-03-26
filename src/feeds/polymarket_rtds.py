"""
Polymarket RTDS WebSocket feed for Chainlink BTC/USD prices.

This module connects to the Polymarket RTDS WebSocket stream,
subscribes to the Chainlink BTC/USD price feed, and maintains
the current price and price_to_beat for the active 5-minute window.

Format validé live le 26 mars 2026 :
- Subscribe  : {"action":"subscribe","subscriptions":[{"topic":"crypto_prices_chainlink","type":"*","filters":"{\"symbol\":\"btc/usd\"}"}]}
- Messages   : {"payload":{"data":[{"timestamp":1774510674000,"value":69997.62...}, ...]}}
  → Le prix est dans payload["data"][-1]["value"] (tableau de points, prendre le dernier)
- Keepalive  : text frame "PING" toutes les 5s (pas RFC 6455 ping)
- Header     : Origin: https://polymarket.com requis
"""

import asyncio
import json
import time
from dataclasses import dataclass
from typing import Optional

import aiohttp
import orjson
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
        self.price_to_beat: Optional[float] = None  # Set by TradingLoop via set_price_to_beat()
        self.reconnect_attempts: int = 0
        self.max_reconnect_delay: int = 30
        self.ws: aiohttp.ClientWebSocketResponse | None = None
        self._session: aiohttp.ClientSession | None = None
        self.last_message_ts: float = 0.0

    async def connect(self) -> None:
        """Connect to the Polymarket RTDS WebSocket stream.

        Starts both the listener and the PING keepalive loop.
        Origin header is required by the RTDS server.
        """
        while True:
            try:
                # Origin header requis par le serveur RTDS
                session = aiohttp.ClientSession(
                    headers={"Origin": "https://polymarket.com"}
                )
                self._session = session
                self.ws = await session.ws_connect(self.ws_url, heartbeat=20.0)
                logger.info("Connected to Polymarket RTDS WebSocket")
                self.reconnect_attempts = 0
                await self._subscribe()
                # Lancer le ping applicatif en parallèle du listener
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

        Format validé live : action + subscriptions[] + filters comme STRING sérialisée.
        Le champ filters DOIT être une string JSON sérialisée (pas un dict).
        """
        if self.ws is None:
            return

        subscribe_message = orjson.dumps({
            "action": "subscribe",
            "subscriptions": [
                {
                    "topic": "crypto_prices_chainlink",
                    "type": "*",
                    # filters DOIT être une string JSON (pas un dict) — bug connu rs-clob-client #136
                    "filters": json.dumps({"symbol": "btc/usd"}),
                }
            ],
        })
        await self.ws.send_str(subscribe_message.decode())
        logger.info("Subscribed to RTDS Chainlink BTC/USD feed")

    async def _ping_loop(self) -> None:
        """Send application-level text PING every 5s to keep the connection alive.

        La doc RTDS indique explicitement : send PING messages every 5 seconds.
        Ce sont des text frames 'PING', pas des RFC 6455 pings.
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
        """Listen for incoming messages from the WebSocket.

        Handles PONG responses (keepalive) and price data messages.
        """
        if self.ws is None:
            return

        async for msg in self.ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                # Garde PONG — réponse au PING applicatif
                if msg.data == "PONG":
                    self.last_message_ts = time.monotonic()
                    logger.debug("PONG received from RTDS")
                    continue
                try:
                    data = orjson.loads(msg.data)
                    logger.debug(
                        "Raw WS message received",
                        data_preview=str(msg.data)[:100],
                    )
                    self._handle_message(data)
                    self.last_message_ts = time.monotonic()
                except Exception as e:
                    logger.error("Failed to parse RTDS message", error=str(e))
            elif msg.type == aiohttp.WSMsgType.PONG:
                # RFC 6455 pong (géré aussi par heartbeat aiohttp)
                self.last_message_ts = time.monotonic()
            elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                break

    def _handle_message(self, data: dict) -> None:
        """Handle incoming RTDS messages.

        Format réel validé live le 26 mars 2026 :
        {"payload": {"data": [{"timestamp": 1774510674000, "value": 69997.62}, ...]}}

        Le prix est dans payload["data"][-1]["value"] (prendre le point le plus récent).
        Fallback sur payload["value"] pour compatibilité avec les messages unitaires
        documentés ({"topic": "...", "type": "update", "payload": {"value": 67234.50}}).

        La price_to_beat est gérée par TradingLoop via set_price_to_beat(), pas ici.

        Args:
            data: Raw RTDS message dict.
        """
        try:
            payload = data.get("payload", {})
            if not payload:
                return

            price_value: Optional[float] = None

            # Format batch (validé live) : payload.data[] = tableau de points
            data_points = payload.get("data")
            if data_points and isinstance(data_points, list) and len(data_points) > 0:
                # Prendre le point le plus récent (dernier du tableau)
                latest = data_points[-1]
                raw_value = latest.get("value")
                if raw_value is not None:
                    price_value = float(raw_value)

            # Fallback format unitaire documenté : payload.value (float direct)
            elif "value" in payload:
                price_value = float(payload["value"])

            # Fallback format documenté avec topic/type
            elif data.get("type") == "update" and data.get("topic") == "crypto_prices_chainlink":
                raw_value = payload.get("value")
                if raw_value is not None:
                    price_value = float(raw_value)

            if price_value is not None:
                self.current_price = price_value
                logger.debug("Chainlink price updated", price=self.current_price)

        except (KeyError, ValueError, TypeError, IndexError) as e:
            logger.error(
                "Failed to handle RTDS message",
                error=str(e),
                data_preview=str(data)[:200],
            )

    async def _reconnect(self) -> None:
        """Reconnect with exponential backoff."""
        delay = min(2 ** self.reconnect_attempts, self.max_reconnect_delay)
        logger.info("Reconnecting to Polymarket RTDS WebSocket", delay=delay)
        await asyncio.sleep(delay)
        self.reconnect_attempts += 1

    def set_price_to_beat(self, price: float) -> None:
        """Set the opening price for the current 5-minute window.

        Called by TradingLoop at window T=0 after reading get_chainlink_price().
        There is no 'window_start' event in the RTDS API — this must be called
        explicitly by the trading loop.

        Args:
            price: Chainlink BTC/USD price at window opening.
        """
        self.price_to_beat = price
        logger.info("Price to beat set for new window", price_to_beat=price)

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

    def get_price_to_beat(self) -> Optional[float]:
        """Get the price to beat for the current 5-minute window.

        Set by TradingLoop at T=0 via set_price_to_beat().

        Returns:
            Price to beat or None if not available.
        """
        return self.price_to_beat