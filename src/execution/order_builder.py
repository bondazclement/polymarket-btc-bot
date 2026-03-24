"""
Order builder module for the Polymarket BTC UpDown 5m trading bot.

This module provides functions to build and sign orders for Polymarket.
"""

from typing import Optional

from py_clob_client.client import ClobClient
from py_clob_client import OrderArgs
from structlog import get_logger

from src.config import CONFIG


logger = get_logger(__name__)


async def build_order(
    client: ClobClient, token_id: str, side: str, price: float, size: float
) -> Optional[OrderArgs]:
    """Build and sign an order for Polymarket.

    Args:
        client: Polymarket CLOB client.
        token_id: Token ID for the order.
        side: Side of the order ("Up" or "Down").
        price: Price of the token.
        size: Size of the order in USDC.

    Returns:
        Signed OrderArgs object or None if order building fails.
    """
    try:
        # Fetch the dynamic fee rate
        fee_rate_bps = await client.get_fee_rate_bps()

        # Build the order
        order_args = OrderArgs(
            token_id=token_id,
            side=side,
            price=price,
            size=size,
            fee_rate_bps=fee_rate_bps,
        )

        # Sign the order
        signed_order = await client.sign_order(order_args)

        logger.info("Order built and signed", token_id=token_id, side=side, price=price, size=size)

        return signed_order
    except Exception as e:
        logger.error("Failed to build order", error=str(e))
        return None
