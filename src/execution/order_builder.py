"""
Order builder module for the Polymarket BTC UpDown 5m trading bot.

This module provides functions to build and post orders for Polymarket.
"""

import asyncio

from py_clob_client.clob_types import OrderArgs, OrderType
from py_clob_client.order_builder.constants import BUY
from structlog import get_logger

from src.execution.clob_client import PolymarketClient


logger = get_logger(__name__)


async def build_and_post_order(
    client: PolymarketClient,
    token_id: str,
    side: str,
    price: float,
    size: float,
) -> bool:
    """Build, sign, and post an order to Polymarket.

    Args:
        client: PolymarketClient wrapper instance.
        token_id: Token ID for the order.
        side: Side of the order ("Up" or "Down").
        price: Price of the token.
        size: Size of the order in USDC.

    Returns:
        True if the order was posted successfully, False otherwise.
    """
    try:
        order_args = OrderArgs(
            token_id=token_id,
            price=price,
            size=size,
            side=BUY,
        )
        signed = await asyncio.to_thread(client.client.create_order, order_args)
        resp = await asyncio.to_thread(
            client.client.post_order, signed, OrderType.GTC
        )
        logger.info(
            "Order posted", token_id=token_id, price=price, size=size, resp=resp
        )
        return True
    except Exception as e:
        logger.error("Failed to build/post order", error=str(e))
        return False
