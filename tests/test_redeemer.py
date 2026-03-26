"""Tests for src/execution/redeemer.py."""

import asyncio
from unittest.mock import MagicMock

from src.execution import redeemer


def test_redeem_if_resolved_returns_tuple_payload() -> None:
    """redeem_if_resolved should return (pnl, is_win) on successful redemption."""
    client = MagicMock()
    client.client = MagicMock()
    client.client.redeem = MagicMock(return_value={"status": "ok"})

    async def run_case() -> tuple[float, bool] | None:
        original_is_market_resolved = redeemer._is_market_resolved
        original_get_winning_side = redeemer._get_winning_side
        try:
            redeemer._is_market_resolved = lambda slug: asyncio.sleep(0, result=True)  # type: ignore[assignment]
            redeemer._get_winning_side = lambda slug: asyncio.sleep(0, result="Up")  # type: ignore[assignment]
            return await redeemer.redeem_if_resolved(
                client=client,
                slug="btc-updown-5m-1700000000",
                condition_id="0xabc",
                side="Up",
                entry_price=0.5,
                entry_size=2.5,
            )
        finally:
            redeemer._is_market_resolved = original_is_market_resolved
            redeemer._get_winning_side = original_get_winning_side

    result = asyncio.run(run_case())
    assert isinstance(result, tuple)
    assert len(result) == 2
    pnl, is_win = result
    assert is_win is True
    assert pnl > 0
