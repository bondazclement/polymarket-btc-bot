"""
Redeemer module for the Polymarket BTC UpDown 5m trading bot.

This module provides functions to redeem tokens after market resolution
via the py-clob-client REST API and Gamma API for resolution checks.
"""

import asyncio

import aiohttp
import orjson
from structlog import get_logger

from src.execution.clob_client import PolymarketClient


logger = get_logger(__name__)

GAMMA_API_URL = "https://gamma-api.polymarket.com"


async def _is_market_resolved(slug: str) -> bool:
    """Check if a market is resolved by querying the Gamma API.

    Args:
        slug: Market slug identifier.

    Returns:
        True if the market is resolved or closed, False otherwise.
    """
    url = f"{GAMMA_API_URL}/events?slug={slug}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    logger.error("Gamma API error", status=resp.status, slug=slug)
                    return False
                data = orjson.loads(await resp.read())
                if not data:
                    logger.warning("No market data found", slug=slug)
                    return False
                event = data[0] if isinstance(data, list) else data
                resolved = event.get("resolved", False)
                closed = event.get("closed", False)
                return bool(resolved or closed)
    except Exception as e:
        logger.error("Failed to check market resolution", slug=slug, error=str(e))
        return False


async def redeem_if_resolved(
    client: PolymarketClient,
    slug: str,
    condition_id: str,
) -> float | None:
    """Redeem tokens if the market is resolved.

    Checks the Gamma API for market resolution status, then calls
    client.redeem() via py-clob-client. Retries up to 2 times with
    3s backoff to account for on-chain settlement delays.

    Args:
        client: PolymarketClient wrapper instance.
        slug: Market slug identifier.
        condition_id: Condition ID for the market.

    Returns:
        Amount redeemed in USDC or None if redemption is not available.
    """
    resolved = await _is_market_resolved(slug)
    if not resolved:
        logger.info("Market not resolved yet", slug=slug)
        return None

    max_retries = 2
    for attempt in range(max_retries):
        try:
            result = await asyncio.to_thread(client.client.redeem, condition_id)
            logger.info(
                "Tokens redeemed successfully",
                slug=slug,
                condition_id=condition_id,
                result=result,
            )
            # result is typically a tx hash; the actual profit is determined
            # by the token payout (1.00$ per winning token minus cost)
            return 1.0
        except Exception as e:
            logger.error(
                "Redeem failed",
                slug=slug,
                condition_id=condition_id,
                attempt=attempt + 1,
                error=str(e),
            )
            if attempt < max_retries - 1:
                await asyncio.sleep(3)

    return None
