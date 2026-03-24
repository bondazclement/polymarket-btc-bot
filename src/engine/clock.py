"""
Clock module for the Polymarket BTC UpDown 5m trading bot.

This module provides functions to manage the timing of trading windows
and synchronize with the 5-minute market cycles.
"""

import asyncio
import time


def get_window_start() -> int:
    """Get the Unix timestamp of the start of the current 5-minute window.

    Returns:
        Unix timestamp of the window start.
    """
    current_time = int(time.time())
    window_start = current_time - (current_time % 300)
    return window_start


def get_time_remaining() -> float:
    """Get the remaining time in the current 5-minute window.

    Returns:
        Remaining time in seconds.
    """
    current_time = time.time()
    window_end = get_window_start() + 300
    return window_end - current_time


async def sleep_until(target_seconds_before_close: int) -> None:
    """Sleep until a specific number of seconds before the window closes.

    Args:
        target_seconds_before_close: Number of seconds before the window closes to wake up.
    """
    while True:
        remaining = get_time_remaining()
        if remaining <= target_seconds_before_close:
            break
        await asyncio.sleep(min(remaining - target_seconds_before_close, 1.0))
