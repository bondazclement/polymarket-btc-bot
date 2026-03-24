"""
Redeemer module for the Polymarket BTC UpDown 5m trading bot.

This module provides functions to redeem tokens after market resolution.
"""

from typing import Optional

from py_clob_client.client import ClobClient
from structlog import get_logger


logger = get_logger(__name__)


async def redeem_if_resolved(client: ClobClient, condition_id: str) -> Optional[float]:
    """Redeem tokens if the market is resolved.

    Args:
        client: Polymarket CLOB client.
        condition_id: Condition ID to check for resolution.

    Returns:
        Amount redeemed in USDC or None if redemption fails.
    """
    try:
        # Check if the market is resolved
        is_resolved = await client.is_market_resolved(condition_id)
        if not is_resolved:
            logger.info("Market not resolved yet", condition_id=condition_id)
            return None

        # Redeem the tokens
        amount = await client.redeem_tokens(condition_id)
        logger.info("Tokens redeemed successfully", condition_id=condition_id, amount=amount)
        return amount
    except Exception as e:
        logger.error("Failed to redeem tokens", condition_id=condition_id, error=str(e))
        return None
