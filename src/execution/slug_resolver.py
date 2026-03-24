"""
Slug resolver module for the Polymarket BTC UpDown 5m trading bot.

This module provides functions to resolve the current market slug and token IDs.
"""

import time
from typing import Tuple

import aiohttp
import orjson
from structlog import get_logger

from src.config import CONFIG


logger = get_logger(__name__)


def get_current_slug(timestamp: int = None) -> str:
    """Get the current market slug for the 5-minute window.

    Args:
        timestamp: Optional timestamp to use for slug generation. If None, uses current time.

    Returns:
        Current market slug as a string.
    """
    if timestamp is None:
        timestamp = int(time.time())

    # Calculate the window start time (multiple of 300 seconds)
    window_start = timestamp - (timestamp % 300)

    # Generate the slug
    slug = f"btc-updown-5m-{window_start}"

    return slug


async def resolve_token_ids(slug: str) -> Tuple[str, str]:
    """Resolve the token IDs for the given market slug.

    Args:
        slug: Market slug to resolve.

    Returns:
        Tuple containing the Up token ID and Down token ID.
    """
    url = f"https://gamma-api.polymarket.com/events?slug={slug}"

    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url) as response:
                if response.status == 200:
                    data = orjson.loads(await response.text())
                    up_token_id = data.get("up_token_id", "")
                    down_token_id = data.get("down_token_id", "")
                    return up_token_id, down_token_id
                else:
                    logger.error("Failed to resolve token IDs", status=response.status)
                    return "", ""
        except Exception as e:
            logger.error("Error resolving token IDs", error=str(e))
            return "", ""
