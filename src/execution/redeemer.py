"""
Redeemer module for the Polymarket BTC UpDown 5m trading bot.

This module provides functions to redeem tokens after market resolution
via the py-clob-client REST API and Gamma API for resolution checks.
"""

import asyncio
from typing import Optional

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


async def _get_winning_side(slug: str) -> Optional[str]:
    """Determine the winning side from Gamma API outcomePrices.

    Args:
        slug: Market slug identifier.

    Returns:
        "Up" or "Down" if determinable, None otherwise.
    """
    url = f"{GAMMA_API_URL}/events?slug={slug}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    return None
                data = orjson.loads(await resp.read())
                if not data:
                    return None
                event = data[0] if isinstance(data, list) else data
                markets = event.get("markets", [])
                if not markets:
                    return None

                market = markets[0]
                outcome_prices = market.get("outcomePrices", [])
                outcomes = market.get("outcomes", [])

                if not outcome_prices or not outcomes:
                    return None

                # outcomePrices are strings like "1" or "0"
                for i, price_str in enumerate(outcome_prices):
                    price = float(price_str)
                    if price >= 0.99 and i < len(outcomes):
                        return str(outcomes[i])

                return None
    except Exception as e:
        logger.error("Failed to get winning side", slug=slug, error=str(e))
        return None


async def redeem_if_resolved(
    client: PolymarketClient,
    slug: str,
    condition_id: str,
    side: str = "",
    entry_price: float = 0.0,
    entry_size: float = 0.0,
) -> float | None:
    """Redeem tokens if the market is resolved.

    Checks the Gamma API for market resolution status, determines win/loss
    via outcomePrices, then calls client.redeem() via py-clob-client.
    Retries up to 2 times with 3s backoff for on-chain settlement delays.

    Args:
        client: PolymarketClient wrapper instance.
        slug: Market slug identifier.
        condition_id: Condition ID for the market.
        side: Side we bought ("Up" or "Down").
        entry_price: Price at which the token was bought.
        entry_size: Size of the order in USDC.

    Returns:
        P&L amount in USDC or None if redemption is not available.
    """
    resolved = await _is_market_resolved(slug)
    if not resolved:
        logger.info("Market not resolved yet", slug=slug)
        return None

    # Determine if we won or lost
    winning_side = await _get_winning_side(slug)
    is_win = winning_side is not None and winning_side == side

    logger.info(
        "Market resolved",
        slug=slug,
        winning_side=winning_side,
        our_side=side,
        is_win=is_win,
    )

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

            # Calculate actual P&L based on win/loss
            if entry_price > 0 and entry_size > 0:
                num_tokens = entry_size / entry_price
                if is_win:
                    # Token pays $1.00 on win
                    pnl = (1.0 - entry_price) * num_tokens
                else:
                    # Token pays $0.00 on loss — we lose our entire entry
                    pnl = -entry_size
                logger.info(
                    "P&L calculated",
                    pnl=pnl,
                    is_win=is_win,
                    entry_price=entry_price,
                    num_tokens=num_tokens,
                )
                return pnl
            else:
                logger.warning("Entry data not available, returning estimate")
                return 0.0
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
