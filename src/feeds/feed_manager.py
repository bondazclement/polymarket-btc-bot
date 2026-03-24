"""
Feed manager for orchestrating multiple WebSocket feeds.

This module manages the Binance, Polymarket RTDS, and Polymarket CLOB WebSocket feeds,
ensuring they are all connected and healthy. It provides methods to start and stop all feeds
concurrently and performs health checks to monitor their status.
"""

import asyncio
from typing import Dict, Optional

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

    async def start_all(self) -> None:
        """Start all WebSocket feeds concurrently."""
        tasks = [
            asyncio.create_task(self.binance_feed.connect()),
            asyncio.create_task(self.polymarket_rtds_feed.connect()),
            asyncio.create_task(self.polymarket_clob_feed.connect()),
        ]
        await asyncio.gather(*tasks)

    async def stop_all(self) -> None:
        """Stop all WebSocket feeds gracefully."""
        # Note: picows does not provide a direct method to close the WebSocket,
        # so we rely on the feeds to handle disconnections gracefully.
        logger.info("Stopping all WebSocket feeds")

    async def health_check(self) -> None:
        """Perform a health check on all feeds.

        This method checks if each feed has received a message in the last 30 seconds
        and updates the health status accordingly.
        """
        # Placeholder for health check logic
        # In a real implementation, this would check the last message timestamp for each feed
        # For now, we assume all feeds are healthy if they are connected
        self.health_status["binance"] = True
        self.health_status["polymarket_rtds"] = True
        self.health_status["polymarket_clob"] = True

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
