"""
Geo-checker module for the Polymarket BTC UpDown 5m trading bot setup CLI.

Tests connectivity to all required endpoints: Binance WS, Polymarket CLOB REST,
and Polymarket RTDS. Detects potential geoblocking issues.

This module is fully independent from src/ — no src/ imports.
"""

import asyncio
import time
from typing import Any, Dict, List, Tuple

import aiohttp


BINANCE_WS_URLS: List[str] = [
    "wss://stream.binance.com:9443/ws/btcusdt@aggTrade",
    "wss://stream.binance.vision/ws/btcusdt@aggTrade",
]

CLOB_REST_URL = "https://clob.polymarket.com"
GAMMA_API_URL = "https://gamma-api.polymarket.com"


async def check_binance_ws() -> Tuple[bool, str]:
    """Test Binance WebSocket connectivity, trying multiple URLs.

    Returns:
        Tuple of (success, working_url or error message).
    """
    for url in BINANCE_WS_URLS:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.ws_connect(
                    url, timeout=aiohttp.ClientTimeout(total=10)
                ) as ws:
                    # Wait for first message (aggTrade tick)
                    msg = await asyncio.wait_for(ws.receive(), timeout=5.0)
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        return True, url
        except Exception:
            continue
    return False, "All Binance WS URLs failed (possible geoblock)"


async def check_clob_rest() -> Tuple[bool, str]:
    """Test Polymarket CLOB REST connectivity.

    Returns:
        Tuple of (success, detail message).
    """
    try:
        async with aiohttp.ClientSession() as session:
            start = time.perf_counter()
            async with session.get(
                f"{CLOB_REST_URL}/ok",
                timeout=aiohttp.ClientTimeout(total=5),
            ) as resp:
                body = await resp.text()
                elapsed_ms = (time.perf_counter() - start) * 1000
                if resp.status == 200 and "OK" in body:
                    return True, f"OK ({elapsed_ms:.0f}ms)"
                return False, f"Unexpected response: {resp.status} {body[:100]}"
    except Exception as e:
        return False, f"Connection failed: {e}"


async def check_gamma_api() -> Tuple[bool, str]:
    """Test Polymarket Gamma API connectivity.

    Returns:
        Tuple of (success, detail message).
    """
    try:
        async with aiohttp.ClientSession() as session:
            start = time.perf_counter()
            async with session.get(
                f"{GAMMA_API_URL}/events?limit=1",
                timeout=aiohttp.ClientTimeout(total=5),
            ) as resp:
                elapsed_ms = (time.perf_counter() - start) * 1000
                if resp.status == 200:
                    return True, f"OK ({elapsed_ms:.0f}ms)"
                return False, f"HTTP {resp.status}"
    except Exception as e:
        return False, f"Connection failed: {e}"


async def run_geo_checks() -> Tuple[bool, Dict[str, Any]]:
    """Run all geo/connectivity checks.

    Returns:
        Tuple of (all_passed, results dict).
    """
    print("\n" + "=" * 50)
    print("GEO & CONNECTIVITY CHECKS")
    print("=" * 50)

    results: Dict[str, Any] = {}
    all_passed = True

    # Binance WS
    binance_ok, binance_detail = await check_binance_ws()
    results["binance_ws"] = {"passed": binance_ok, "detail": binance_detail}
    symbol = "\u2705" if binance_ok else "\u274c"
    print(f"  {symbol} Binance WS: {binance_detail}")
    all_passed = all_passed and binance_ok

    # CLOB REST
    clob_ok, clob_detail = await check_clob_rest()
    results["clob_rest"] = {"passed": clob_ok, "detail": clob_detail}
    symbol = "\u2705" if clob_ok else "\u274c"
    print(f"  {symbol} CLOB REST: {clob_detail}")
    all_passed = all_passed and clob_ok

    # Gamma API
    gamma_ok, gamma_detail = await check_gamma_api()
    results["gamma_api"] = {"passed": gamma_ok, "detail": gamma_detail}
    symbol = "\u2705" if gamma_ok else "\u274c"
    print(f"  {symbol} Gamma API: {gamma_detail}")
    all_passed = all_passed and gamma_ok

    results["passed"] = all_passed
    return all_passed, results
