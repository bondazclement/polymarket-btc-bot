"""
Slug resolver module for the Polymarket BTC UpDown 5m trading bot.

This module provides functions to resolve the current market slug,
token IDs, and condition ID via the Gamma API.
"""

import time
from dataclasses import dataclass
from typing import Optional

import aiohttp
import orjson
from structlog import get_logger


logger = get_logger(__name__)


@dataclass(slots=True)
class MarketData:
    """Resolved market data for a 5-minute window.

    Attributes:
        slug: Market slug identifier.
        condition_id: On-chain condition ID for the market.
        up_token_id: CLOB token ID for the Up outcome.
        down_token_id: CLOB token ID for the Down outcome.
    """

    slug: str
    condition_id: str
    up_token_id: str
    down_token_id: str


def get_current_slug(timestamp: Optional[int] = None) -> str:
    """Get the current market slug for the 5-minute window.

    Args:
        timestamp: Optional timestamp to use for slug generation. If None, uses current time.

    Returns:
        Current market slug as a string.
    """
    if timestamp is None:
        timestamp = int(time.time())

    window_start = timestamp - (timestamp % 300)
    slug = f"btc-updown-5m-{window_start}"

    return slug


async def resolve_market_data(slug: str) -> Optional[MarketData]:
    """Resolve all market data for the given slug via Gamma API.

    Args:
        slug: Market slug identifier.

    Returns:
        MarketData with token IDs and condition ID, or None on failure.
    """
    url = f"https://gamma-api.polymarket.com/events?slug={slug}"

    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(
                url, timeout=aiohttp.ClientTimeout(total=5)
            ) as response:
                if response.status != 200:
                    logger.error("Gamma API error", status=response.status, slug=slug)
                    return None

                data = orjson.loads(await response.read())

                if not data or not isinstance(data, list):
                    logger.error("Empty or invalid Gamma response", slug=slug)
                    return None

                event = data[0]
                markets = event.get("markets", [])
                if not markets:
                    logger.error("No markets found in event", slug=slug)
                    return None

                market = markets[0]
                condition_id = market.get("conditionId", "")
                clob_token_ids = market.get("clobTokenIds", [])
                outcomes = market.get("outcomes", [])

                if len(clob_token_ids) < 2 or len(outcomes) < 2:
                    logger.error("Incomplete market data", slug=slug)
                    return None

                up_idx = outcomes.index("Up") if "Up" in outcomes else 0
                down_idx = outcomes.index("Down") if "Down" in outcomes else 1

                return MarketData(
                    slug=slug,
                    condition_id=condition_id,
                    up_token_id=clob_token_ids[up_idx],
                    down_token_id=clob_token_ids[down_idx],
                )
        except Exception as e:
            logger.error("Error resolving market data", slug=slug, error=str(e))
            return None


async def resolve_token_ids(slug: str) -> tuple[str, str]:
    """Resolve the token IDs for the given market slug.

    Wrapper around resolve_market_data for backward compatibility.

    Args:
        slug: Market slug to resolve.

    Returns:
        Tuple containing the Up token ID and Down token ID.
    """
    market = await resolve_market_data(slug)
    if market is None:
        return "", ""
    return market.up_token_id, market.down_token_id
