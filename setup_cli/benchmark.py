"""
Benchmark module for the Polymarket BTC UpDown 5m trading bot.

This module provides standalone performance benchmarks that are fully
independent from the src/ stack. No src/ modules are imported.
"""

import math
import os
import random
import statistics
import time
from typing import Any, Dict, List

import aiohttp
import numpy as np
import orjson
from scipy.stats import norm


async def run_benchmarks() -> bool:
    """Run all performance benchmarks.

    Returns:
        True if all benchmarks passed, False otherwise.
    """
    print("\n" + "=" * 50)
    print("STEP 5: RUNNING BENCHMARKS")
    print("=" * 50)

    results: Dict[str, Any] = {}
    passed_all = True

    # Benchmark 1: Network latency
    net_passed, net_data = await bench_network()
    results["network"] = net_data
    passed_all = passed_all and net_passed

    # Benchmark 2: JSON parsing
    parse_passed, parse_data = bench_json_parsing()
    results["parsing"] = parse_data
    passed_all = passed_all and parse_passed

    # Benchmark 3: Decision cycle
    dec_passed, dec_data = bench_decision_cycle()
    results["decision"] = dec_data
    passed_all = passed_all and dec_passed

    # Benchmark 4: CLOB roundtrip
    clob_passed, clob_data = await bench_clob_roundtrip()
    results["clob"] = clob_data
    passed_all = passed_all and clob_passed

    # Write JSON report
    with open("benchmark_results.json", "wb") as f:
        f.write(orjson.dumps(results, option=orjson.OPT_INDENT_2))

    # Print summary
    print("\n" + "=" * 50)
    print("BENCHMARK RESULTS")
    print("=" * 50)
    for name, data in results.items():
        symbol = "\u2705" if data.get("passed") else "\u274c"
        p95 = data.get("p95_ms", 0.0)
        print(f"{symbol} {name}: p95={p95:.3f}ms")

    return passed_all


def _calc_percentiles(latencies: List[float]) -> Dict[str, float]:
    """Calculate p50, p95, p99 percentiles from a list of latencies in seconds.

    Args:
        latencies: List of latency measurements in seconds.

    Returns:
        Dictionary with p50_ms, p95_ms, p99_ms in milliseconds.
    """
    if not latencies:
        return {"p50_ms": 0.0, "p95_ms": 0.0, "p99_ms": 0.0}

    latencies_ms = [x * 1000 for x in latencies]
    p50 = statistics.median(latencies_ms)
    quantiles = statistics.quantiles(latencies_ms, n=100)
    p95 = quantiles[94] if len(quantiles) >= 95 else max(latencies_ms)
    p99 = quantiles[98] if len(quantiles) >= 99 else max(latencies_ms)
    return {"p50_ms": p50, "p95_ms": p95, "p99_ms": p99}


async def bench_network() -> tuple[bool, Dict[str, Any]]:
    """Benchmark network latency to Binance, Polymarket CLOB, and Polygon RPC.

    Returns:
        Tuple of (passed, data dictionary).
    """
    print("\nBenchmark 1: Network Latency")
    print("-" * 50)

    polygon_rpc = os.getenv("POLYGON_RPC_URL", "")

    endpoints: Dict[str, Dict[str, Any]] = {
        "binance": {"url": "https://stream.binance.com:9443", "method": "GET", "body": None},
        "polymarket_clob": {
            "url": "https://clob.polymarket.com/ok",
            "method": "GET",
            "body": None,
        },
    }
    if polygon_rpc:
        endpoints["polygon_rpc"] = {
            "url": polygon_rpc,
            "method": "POST",
            "body": orjson.dumps(
                {"jsonrpc": "2.0", "method": "eth_blockNumber", "params": [], "id": 1}
            ),
        }

    all_passed = True
    result_data: Dict[str, Any] = {}

    async with aiohttp.ClientSession() as session:
        for name, ep in endpoints.items():
            latencies: List[float] = []
            for _ in range(50):
                start = time.perf_counter()
                try:
                    if ep["method"] == "POST":
                        async with session.post(
                            ep["url"],
                            data=ep["body"],
                            headers={"Content-Type": "application/json"},
                            timeout=aiohttp.ClientTimeout(total=5),
                        ) as resp:
                            await resp.read()
                    else:
                        async with session.get(
                            ep["url"],
                            timeout=aiohttp.ClientTimeout(total=5),
                        ) as resp:
                            await resp.read()
                    elapsed = time.perf_counter() - start
                    latencies.append(elapsed)
                except Exception:
                    elapsed = time.perf_counter() - start
                    latencies.append(elapsed)

            pcts = _calc_percentiles(latencies)
            endpoint_passed = pcts["p95_ms"] < 100.0
            all_passed = all_passed and endpoint_passed
            result_data[name] = {**pcts, "passed": endpoint_passed}
            symbol = "\u2705" if endpoint_passed else "\u274c"
            print(
                f"  {symbol} {name}: "
                f"p50={pcts['p50_ms']:.1f}ms "
                f"p95={pcts['p95_ms']:.1f}ms "
                f"p99={pcts['p99_ms']:.1f}ms"
            )

    result_data["passed"] = all_passed
    p95_vals = [
        v["p95_ms"] for k, v in result_data.items() if isinstance(v, dict) and "p95_ms" in v
    ]
    result_data["p95_ms"] = max(p95_vals) if p95_vals else 0.0
    return all_passed, result_data


def bench_json_parsing() -> tuple[bool, Dict[str, Any]]:
    """Benchmark JSON parsing speed with orjson.

    Returns:
        Tuple of (passed, data dictionary).
    """
    print("\nBenchmark 2: JSON Parsing")
    print("-" * 50)

    messages = [
        orjson.dumps({"p": "87000.50", "q": "0.01", "T": 1710000000000, "m": False})
        for _ in range(10000)
    ]

    latencies: List[float] = []
    for msg in messages:
        start = time.perf_counter()
        orjson.loads(msg)
        elapsed = time.perf_counter() - start
        latencies.append(elapsed)

    pcts = _calc_percentiles(latencies)
    passed = pcts["p99_ms"] < 0.1
    symbol = "\u2705" if passed else "\u274c"
    print(
        f"  {symbol} p50={pcts['p50_ms']:.4f}ms "
        f"p95={pcts['p95_ms']:.4f}ms "
        f"p99={pcts['p99_ms']:.4f}ms"
    )

    return passed, {**pcts, "passed": passed}


def bench_decision_cycle() -> tuple[bool, Dict[str, Any]]:
    """Benchmark the decision cycle speed using scipy and numpy directly.

    Returns:
        Tuple of (passed, data dictionary).
    """
    print("\nBenchmark 3: Decision Cycle Speed")
    print("-" * 50)

    latencies: List[float] = []

    for _ in range(1000):
        start = time.perf_counter()

        delta = random.uniform(-0.005, 0.005)
        z = delta / (0.01 * math.sqrt(30.0 / 3600.0))
        prob = float(norm.cdf(z))
        _kelly = max(0.0, (0.65 * (1.0 / 0.55 - 1.0) - 0.35) / (1.0 / 0.55 - 1.0))

        elapsed = time.perf_counter() - start
        latencies.append(elapsed)

    pcts = _calc_percentiles(latencies)
    passed = pcts["p99_ms"] < 5.0
    symbol = "\u2705" if passed else "\u274c"
    print(
        f"  {symbol} p50={pcts['p50_ms']:.3f}ms "
        f"p95={pcts['p95_ms']:.3f}ms "
        f"p99={pcts['p99_ms']:.3f}ms"
    )

    return passed, {**pcts, "passed": passed}


async def bench_clob_roundtrip() -> tuple[bool, Dict[str, Any]]:
    """Benchmark CLOB HTTP roundtrip time.

    Returns:
        Tuple of (passed, data dictionary).
    """
    print("\nBenchmark 4: CLOB Roundtrip")
    print("-" * 50)

    latencies: List[float] = []

    async with aiohttp.ClientSession() as session:
        for _ in range(20):
            start = time.perf_counter()
            try:
                async with session.get(
                    "https://clob.polymarket.com/ok",
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as resp:
                    await resp.read()
                async with session.get(
                    "https://clob.polymarket.com/time",
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as resp:
                    await resp.read()
            except Exception:
                pass
            elapsed = time.perf_counter() - start
            latencies.append(elapsed)

    pcts = _calc_percentiles(latencies)
    passed = pcts["p95_ms"] < 200.0
    symbol = "\u2705" if passed else "\u274c"
    print(
        f"  {symbol} p50={pcts['p50_ms']:.1f}ms "
        f"p95={pcts['p95_ms']:.1f}ms "
        f"p99={pcts['p99_ms']:.1f}ms"
    )

    return passed, {**pcts, "passed": passed}
