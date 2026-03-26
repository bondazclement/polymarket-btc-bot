"""
Feed manager for orchestrating multiple WebSocket feeds.

This module manages the Binance, Polymarket RTDS, and Polymarket CLOB WebSocket feeds,
ensuring they are all connected and healthy. It provides methods to start and stop all feeds
concurrently and performs health checks to monitor their status.
"""

import asyncio
import time
from typing import Any, Dict, List

from structlog import get_logger

from src.feeds.binance_ws import BinanceWebSocket
from src.feeds.polymarket_clob_ws import PolymarketCLOBWebSocket
from src.feeds.polymarket_rtds import PolymarketRTDS


logger = get_logger(__name__)


class FeedManager:
    """Manager for orchestrating multiple WebSocket feeds.

    Attributes:
        binance_feed: Binance WebSocket feed.
        polymarket_rtds_feed: Polymarket RTDS WebSocket feed.
        polymarket_clob_feed: Polymarket CLOB WebSocket feed.
        health_status: Dictionary tracking the health status of each feed.
    """

    def __init__(self) -> None:
        """Initialize the FeedManager with all feed instances."""
        self.binance_feed: BinanceWebSocket = BinanceWebSocket()
        self.polymarket_rtds_feed: PolymarketRTDS = PolymarketRTDS()
        self.polymarket_clob_feed: PolymarketCLOBWebSocket = PolymarketCLOBWebSocket()
        self.health_status: Dict[str, bool] = {
            "binance": False,
            "polymarket_rtds": False,
            "polymarket_clob": False,
        }
        self._tasks: List[asyncio.Task[Any]] = []

    async def start_all(self) -> None:
        """Start all WebSocket feeds and health monitor as background tasks."""
        self._tasks = [
            asyncio.create_task(self.binance_feed.connect()),
            asyncio.create_task(self.polymarket_rtds_feed.connect()),
            asyncio.create_task(self.polymarket_clob_feed.connect()),
            asyncio.create_task(self.monitor_health()),
        ]

    async def stop_all(self) -> None:
        """Stop all WebSocket feeds gracefully."""
        logger.info("Stopping all WebSocket feeds")
        for task in self._tasks:
            task.cancel()
        self._tasks.clear()

    async def health_check(self) -> None:
        """Perform a health check on all feeds.

        Checks if each feed has received a message in the last 30 seconds
        and updates the health status accordingly.
        """
        now = time.monotonic()

        # Per-feed stale thresholds: CLOB order book updates are less frequent
        thresholds: Dict[str, float] = {
            "binance": 30.0,
            "polymarket_rtds": 30.0,
            "polymarket_clob": 120.0,
        }

        feeds: Dict[str, Any] = {
            "binance": self.binance_feed,
            "polymarket_rtds": self.polymarket_rtds_feed,
            "polymarket_clob": self.polymarket_clob_feed,
        }

        for name, feed in feeds.items():
            last_ts = feed.get_last_message_ts()
            if name == "polymarket_rtds":
                last_price_ts = feed.get_last_price_ts()
                if last_price_ts > 0.0:
                    last_ts = max(last_ts, last_price_ts)
            if last_ts == 0.0:
                self.health_status[name] = False
            else:
                self.health_status[name] = (now - last_ts) < thresholds[name]

        logger.info("Health check completed", status=self.health_status)

    async def monitor_health(self) -> None:
        """Monitor the health of all feeds at regular intervals."""
        while True:
            await self.health_check()
            await asyncio.sleep(60)

    def get_health_status(self) -> Dict[str, bool]:
        """Get the current health status of all feeds.

        Returns:
            Dictionary with the health status of each feed.
        """
        return self.health_status

    def is_healthy(self) -> bool:
        """Check if all feeds are healthy.

        Returns:
            True if all feeds are healthy, False otherwise.
        """
        return all(self.health_status.values())
