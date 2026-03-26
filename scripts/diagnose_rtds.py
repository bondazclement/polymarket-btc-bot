"""Diagnostic utility for Polymarket RTDS Chainlink feed."""

import argparse
import asyncio

import aiohttp
import orjson


RTDS_URL = "wss://ws-live-data.polymarket.com"


async def run_diagnostic(symbol: str, samples: int, timeout: float) -> None:
    """Connect to RTDS, subscribe, and print incoming messages.

    Args:
        symbol: Symbol filter for RTDS (e.g. "btc/usd").
        samples: Number of messages to inspect before exiting.
        timeout: Per-message timeout in seconds.
    """
    headers = {"Origin": "https://polymarket.com"}
    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.ws_connect(RTDS_URL, heartbeat=20.0) as ws:
            payload = {
                "action": "subscribe",
                "subscriptions": [
                    {
                        "topic": "crypto_prices_chainlink",
                        "type": "*",
                        "filters": orjson.dumps({"symbol": symbol}).decode(),
                    }
                ],
            }
            await ws.send_str(orjson.dumps(payload).decode())
            print("SUBSCRIBED", payload)

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
                    print(f"[{i}] PONG")
                    continue

                print(f"[{i}] TEXT {str(msg.data)[:220]}")
                if i % 2 == 1:
                    await ws.send_str("PING")


def main() -> None:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(description="RTDS diagnostics")
    parser.add_argument("--symbol", default="btc/usd", help="Symbol filter (default: btc/usd)")
    parser.add_argument("--samples", type=int, default=20, help="Number of received messages to inspect")
    parser.add_argument("--timeout", type=float, default=8.0, help="Receive timeout seconds")
    args = parser.parse_args()
    asyncio.run(run_diagnostic(symbol=args.symbol, samples=args.samples, timeout=args.timeout))


if __name__ == "__main__":
    main()
