"""
Benchmark module for the Polymarket BTC UpDown 5m trading bot.

This module provides functions to run performance benchmarks for the bot,
including network latency, WebSocket callback performance, decision cycle speed,
and CLOB roundtrip time.
"""

import asyncio
import statistics
import time
from typing import Dict, List

import aiohttp
import numpy as np
import orjson
import picows

from src.config import CONFIG
from src.feeds.binance_ws import BinanceWebSocket
from src.signal.delta import calc_delta
from src.signal.gbm import calc_up_probability
from src.signal.scorer import SignalScorer
from src.strategy.kelly import calc_kelly_bet


async def run_benchmarks() -> bool:
    """Run all performance benchmarks.

    Returns:
        True if all benchmarks passed, False otherwise.
    """
    print("\n" + "=" * 50)
    print("STEP 5: RUNNING BENCHMARKS")
    print("=" * 50)

    results: Dict[str, bool] = {}

    # Benchmark 1: Network latency
    results["Network Latency"] = await bench_network()

    # Benchmark 2: WebSocket callback performance
    results["WebSocket Callback Performance"] = await bench_ws_callback()

    # Benchmark 3: Decision cycle speed
    results["Decision Cycle Speed"] = await bench_decision_cycle()

    # Benchmark 4: CLOB roundtrip time
    results["CLOB Roundtrip Time"] = await bench_clob_roundtrip()

    # Print benchmark results
    print("\n" + "=" * 50)
    print("BENCHMARK RESULTS")
    print("=" * 50)
    for benchmark, passed in results.items():
        symbol = "✅" if passed else "❌"
        print(f"{symbol} {benchmark}")

    return all(results.values())


async def bench_network() -> bool:
    """Benchmark network latency to Binance, Polymarket CLOB, and Polygon RPC.

    Returns:
        True if the benchmark passed, False otherwise.
    """
    print("\nBenchmark 1: Network Latency")
    print("-" * 50)

    urls = [
        CONFIG.BINANCE_WS_URL.replace("wss://", "https://").replace("/ws", ""),
        CONFIG.POLYMARKET_CLOB_URL,
        CONFIG.POLYGON_RPC_URL,
    ]

    latencies: List[float] = []

    async with aiohttp.ClientSession() as session:
        for url in urls:
            try:
                start_time = time.time()
                async with session.get(url, timeout=5) as response:
                    await response.text()
                end_time = time.time()
                latencies.append((end_time - start_time) * 1000)  # Convert to milliseconds
            except Exception as e:
                print(f"❌ Failed to connect to {url}: {e}")
                return False

    p50 = statistics.median(latencies)
    p95 = statistics.median(sorted(latencies)[: int(len(latencies) * 0.95)])
    p99 = statistics.median(sorted(latencies)[: int(len(latencies) * 0.99)])

    print(f"Latencies (ms): p50={p50:.2f}, p95={p95:.2f}, p99={p99:.2f}")

    # Check if p95 is below the threshold
    if p95 < 50:
        print("✅ Network latency benchmark passed")
        return True
    else:
        print("❌ Network latency benchmark failed")
        return False


async def bench_ws_callback() -> bool:
    """Benchmark WebSocket callback performance.

    Returns:
        True if the benchmark passed, False otherwise.
    """
    print("\nBenchmark 2: WebSocket Callback Performance")
    print("-" * 50)

    ws = BinanceWebSocket()
    parsing_times: List[float] = []

    async def on_message(message: str) -> None:
        start_time = time.time()
        data = orjson.loads(message)
        ws.parse_tick(data)
        end_time = time.time()
        parsing_times.append((end_time - start_time) * 1000)  # Convert to milliseconds

    try:
        await ws.connect()
        # Simulate receiving messages (in a real scenario, this would be done via the WebSocket)
        for _ in range(1000):
            await on_message('{"p":"50000.0","q":"0.01","T":123456789,"m":false}')

        p50 = statistics.median(parsing_times)
        p99 = statistics.median(sorted(parsing_times)[: int(len(parsing_times) * 0.99)])

        print(f"Parsing times (ms): p50={p50:.2f}, p99={p99:.2f}")

        # Check if p99 is below the threshold
        if p99 < 2:
            print("✅ WebSocket callback performance benchmark passed")
            return True
        else:
            print("❌ WebSocket callback performance benchmark failed")
            return False
    except Exception as e:
        print(f"❌ WebSocket callback performance benchmark failed: {e}")
        return False


async def bench_decision_cycle() -> bool:
    """Benchmark the decision cycle speed.

    Returns:
        True if the benchmark passed, False otherwise.
    """
    print("\nBenchmark 3: Decision Cycle Speed")
    print("-" * 50)

    decision_times: List[float] = []

    for _ in range(1000):
        start_time = time.time()

        # Simulate a decision cycle
        delta = calc_delta(50000.0, 49900.0)
        gbm_prob = calc_up_probability(delta, 0.01, 300)
        signal_scorer = SignalScorer()
        signal = signal_scorer.score(delta, 0.01, gbm_prob, 50.0, 0.0, 300)
        bet_size = calc_kelly_bet(0.6, 0.5, 100.0, 0.25)

        end_time = time.time()
        decision_times.append((end_time - start_time) * 1000)  # Convert to milliseconds

    p50 = statistics.median(decision_times)
    p99 = statistics.median(sorted(decision_times)[: int(len(decision_times) * 0.99)])

    print(f"Decision times (ms): p50={p50:.2f}, p99={p99:.2f}")

    # Check if p99 is below the threshold
    if p99 < 50:
        print("✅ Decision cycle speed benchmark passed")
        return True
    else:
        print("❌ Decision cycle speed benchmark failed")
        return False


async def bench_clob_roundtrip() -> bool:
    """Benchmark the CLOB roundtrip time.

    Returns:
        True if the benchmark passed, False otherwise.
    """
    print("\nBenchmark 4: CLOB Roundtrip Time")
    print("-" * 50)

    try:
        from py_clob_client.client import ClobClient

        client = ClobClient(
            private_key="",
            funder="",
            api_key="",
            api_secret="",
            passphrase="",
            rpc_url="",
        )

        roundtrip_times: List[float] = []

        for _ in range(10):
            start_time = time.time()

            # Place a limit order at a price that will not be filled
            order = await client.place_order(
                {
                    "token_id": "test_token",
                    "side": "Up",
                    "price": 0.01,
                    "size": 2.50,
                    "fee_rate_bps": 0,
                }
            )

            # Cancel the order immediately
            await client.cancel_order(order["order_id"])

            end_time = time.time()
            roundtrip_times.append((end_time - start_time) * 1000)  # Convert to milliseconds

        p50 = statistics.median(roundtrip_times)
        p95 = statistics.median(sorted(roundtrip_times)[: int(len(roundtrip_times) * 0.95)])

        print(f"Roundtrip times (ms): p50={p50:.2f}, p95={p95:.2f}")

        # Check if p95 is below the threshold
        if p95 < 300:
            print("✅ CLOB roundtrip time benchmark passed")
            return True
        else:
            print("❌ CLOB roundtrip time benchmark failed")
            return False
    except Exception as e:
        print(f"❌ CLOB roundtrip time benchmark failed: {e}")
        return False
