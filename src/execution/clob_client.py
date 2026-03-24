"""
Polymarket CLOB client module for the Polymarket BTC UpDown 5m trading bot.

This module provides a wrapper around the py-clob-client ClobClient for interacting
with the Polymarket CLOB.
"""

import asyncio
from typing import Optional

from py_clob_client.client import ClobClient
from py_clob_client import OrderArgs
from structlog import get_logger

from src.config import CONFIG


logger = get_logger(__name__)


class PolymarketClient:
    """Wrapper around the py-clob-client ClobClient for Polymarket.

    Attributes:
        client: ClobClient instance.
        max_retries: Maximum number of retries for order placement.
    """

    def __init__(self) -> None:
        """Initialize the PolymarketClient with the ClobClient."""
        self.client = ClobClient(
            host=CONFIG.POLYMARKET_CLOB_URL,
            funder=CONFIG.POLYMARKET_FUNDER,
        )
        self.max_retries = 3

    async def place_order(self, order: OrderArgs) -> bool:
        """Place an order on the Polymarket CLOB with retry logic.

        Args:
            order: OrderArgs object to place.

        Returns:
            True if the order was placed successfully, False otherwise.
        """
        for attempt in range(self.max_retries):
            try:
                await self.client.place_order(order)
                logger.info("Order placed successfully", order_id=order.order_id)
                return True
            except Exception as e:
                logger.error("Failed to place order", attempt=attempt + 1, error=str(e))
                if attempt < self.max_retries - 1:
                    delay = 2**attempt  # Exponential backoff
                    logger.info("Retrying order placement", delay=delay)
                    await asyncio.sleep(delay)
        return False

    async def cancel_order(self, order_id: str) -> bool:
        """Cancel an order on the Polymarket CLOB.

        Args:
            order_id: ID of the order to cancel.

        Returns:
            True if the order was cancelled successfully, False otherwise.
        """
        try:
            await self.client.cancel_order(order_id)
            logger.info("Order cancelled successfully", order_id=order_id)
            return True
        except Exception as e:
            logger.error("Failed to cancel order", order_id=order_id, error=str(e))
            return False

    async def cancel_all(self) -> bool:
        """Cancel all open orders on the Polymarket CLOB.

        Returns:
            True if all orders were cancelled successfully, False otherwise.
        """
        try:
            await self.client.cancel_all_orders()
            logger.info("All orders cancelled successfully")
            return True
        except Exception as e:
            logger.error("Failed to cancel all orders", error=str(e))
            return False

    async def get_order_book(self, token_id: str) -> Optional[dict]:
        """Get the order book for a specific token.

        Args:
            token_id: Token ID to get the order book for.

        Returns:
            Order book data as a dictionary or None if the request fails.
        """
        try:
            order_book = await self.client.get_order_book(token_id)
            return order_book
        except Exception as e:
            logger.error("Failed to get order book", token_id=token_id, error=str(e))
            return None
