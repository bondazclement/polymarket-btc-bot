"""Diagnostic utility for Polymarket CLOB market channel."""

import argparse
import asyncio
from collections import Counter
from typing import Any

import aiohttp
import orjson


CLOB_WS_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/market"


async def run_diagnostic(token_ids: list[str], samples: int, timeout: float) -> None:
    """Connect to CLOB WS, subscribe and summarize event types.

    Args:
        token_ids: Asset IDs to subscribe to.
        samples: Maximum frames to process before exit.
        timeout: Per-frame timeout in seconds.
    """
    if not token_ids:
        raise ValueError("token_ids list is empty")

    counts: Counter[str] = Counter()
    async with aiohttp.ClientSession() as session:
        async with session.ws_connect(CLOB_WS_URL, heartbeat=20.0) as ws:
            sub: dict[str, Any] = {
                "assets_ids": token_ids,
                "type": "market",
                "custom_feature_enabled": True,
            }
            await ws.send_str(orjson.dumps(sub).decode())
            await ws.send_str("PING")
            print("SUBSCRIBED", sub)

            for i in range(samples):
                try:
                    msg = await ws.receive(timeout=timeout)
                except TimeoutError:
                    await ws.send_str("PING")
                    print(f"[{i}] TIMEOUT -> sent PING")
                    continue

                if msg.type != aiohttp.WSMsgType.TEXT:
                    print(f"[{i}] {msg.type.name}")
                    continue

                if msg.data == "PONG":
                    counts["PONG"] += 1
                    print(f"[{i}] PONG")
                    continue

                data = orjson.loads(msg.data)
                messages = data if isinstance(data, list) else [data]
                for event in messages:
                    event_type = str(event.get("event_type", "<none>"))
                    counts[event_type] += 1
                    print(
                        f"[{i}] {event_type} asset_id={event.get('asset_id','')} "
                        f"{str(event)[:180]}"
                    )
                if i % 3 == 2:
                    await ws.send_str("PING")

    print("SUMMARY", dict(counts))


def main() -> None:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(description="CLOB WS diagnostics")
    parser.add_argument(
        "--token-id",
        action="append",
        dest="token_ids",
        default=[],
        help="Token ID to subscribe (pass twice for up/down)",
    )
    parser.add_argument("--samples", type=int, default=40, help="Number of frames to inspect")
    parser.add_argument("--timeout", type=float, default=10.0, help="Receive timeout seconds")
    args = parser.parse_args()
    asyncio.run(run_diagnostic(token_ids=args.token_ids, samples=args.samples, timeout=args.timeout))


if __name__ == "__main__":
    main()
