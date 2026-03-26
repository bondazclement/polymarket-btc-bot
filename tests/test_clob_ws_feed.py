"""Tests for src/feeds/polymarket_clob_ws.py"""

import pytest
from unittest.mock import AsyncMock
import orjson

from src.feeds.polymarket_clob_ws import PolymarketCLOBWebSocket


@pytest.fixture
def clob_ws() -> PolymarketCLOBWebSocket:
    """Fixture returning a fresh PolymarketCLOBWebSocket instance."""
    return PolymarketCLOBWebSocket()


def test_handle_book_event_parses_correctly(clob_ws: PolymarketCLOBWebSocket) -> None:
    """book event with object-style bids/asks is parsed into OrderBookLevel."""
    msg = {
        "event_type": "book",
        "asset_id": "0xabc123",
        "bids": [{"price": "0.48", "size": "100"}],
        "asks": [{"price": "0.52", "size": "80"}],
    }
    clob_ws._handle_message(msg)
    assert clob_ws.get_best_ask("0xabc123") == pytest.approx(0.52)
    assert clob_ws.get_best_bid("0xabc123") == pytest.approx(0.48)


def test_handle_best_bid_ask_event(clob_ws: PolymarketCLOBWebSocket) -> None:
    """best_bid_ask event is stored in best_prices cache."""
    msg = {
        "event_type": "best_bid_ask",
        "asset_id": "0xdef456",
        "best_bid": "0.73",
        "best_ask": "0.77",
        "spread": "0.04",
    }
    clob_ws._handle_message(msg)
    assert clob_ws.get_best_ask("0xdef456") == pytest.approx(0.77)
    assert clob_ws.get_best_bid("0xdef456") == pytest.approx(0.73)


def test_best_bid_ask_takes_priority_over_book(clob_ws: PolymarketCLOBWebSocket) -> None:
    """best_prices cache takes priority over order_books fallback."""
    book_msg = {
        "event_type": "book",
        "asset_id": "0xaaa",
        "bids": [{"price": "0.40", "size": "50"}],
        "asks": [{"price": "0.60", "size": "50"}],
    }
    bba_msg = {
        "event_type": "best_bid_ask",
        "asset_id": "0xaaa",
        "best_bid": "0.45",
        "best_ask": "0.55",
        "spread": "0.10",
    }
    clob_ws._handle_message(book_msg)
    clob_ws._handle_message(bba_msg)
    # best_prices cache should win
    assert clob_ws.get_best_ask("0xaaa") == pytest.approx(0.55)
    assert clob_ws.get_best_bid("0xaaa") == pytest.approx(0.45)


def test_handle_list_of_messages(clob_ws: PolymarketCLOBWebSocket) -> None:
    """Messages wrapped in a list are all processed."""
    msgs = [
        {
            "event_type": "book",
            "asset_id": "0x111",
            "bids": [{"price": "0.49", "size": "10"}],
            "asks": [{"price": "0.51", "size": "10"}],
        },
        {
            "event_type": "book",
            "asset_id": "0x222",
            "bids": [{"price": "0.30", "size": "5"}],
            "asks": [{"price": "0.70", "size": "5"}],
        },
    ]
    clob_ws._handle_message(msgs)
    assert clob_ws.get_best_ask("0x111") == pytest.approx(0.51)
    assert clob_ws.get_best_ask("0x222") == pytest.approx(0.70)


def test_get_best_ask_returns_none_if_no_data(clob_ws: PolymarketCLOBWebSocket) -> None:
    """Returns None when token not in any cache."""
    assert clob_ws.get_best_ask("0xnonexistent") is None


def test_get_best_bid_returns_none_if_no_data(clob_ws: PolymarketCLOBWebSocket) -> None:
    """Returns None when token not in any cache."""
    assert clob_ws.get_best_bid("0xnonexistent") is None


def test_handle_message_skips_msg_without_asset_id(clob_ws: PolymarketCLOBWebSocket) -> None:
    """Messages without asset_id are silently skipped."""
    msg = {"event_type": "book", "bids": [], "asks": []}
    clob_ws._handle_message(msg)  # Should not raise
    assert clob_ws.order_books == {}


def test_handle_message_ignores_unknown_event_type(clob_ws: PolymarketCLOBWebSocket) -> None:
    """Unknown event types do not crash and do not populate caches."""
    msg = {"event_type": "price_change", "asset_id": "0xabc", "changes": []}
    clob_ws._handle_message(msg)  # Should not raise
    assert clob_ws.get_best_ask("0xabc") is None


@pytest.mark.asyncio
async def test_subscribe_assets_sends_correct_format() -> None:
    """subscribe_assets sends JSON with type 'market' and assets_ids list."""
    clob_ws = PolymarketCLOBWebSocket()
    mock_ws = AsyncMock()
    mock_ws.closed = False
    clob_ws.ws = mock_ws

    await clob_ws.subscribe_assets(["token_up", "token_down"])

    mock_ws.send_str.assert_called_once()
    sent = orjson.loads(mock_ws.send_str.call_args[0][0])
    assert sent["type"] == "market"
    assert "assets_ids" in sent
    assert "token_up" in sent["assets_ids"]
    assert "token_down" in sent["assets_ids"]
    assert sent.get("custom_feature_enabled") is True


@pytest.mark.asyncio
async def test_subscribe_assets_noop_when_not_connected() -> None:
    """subscribe_assets does not raise when ws is None."""
    clob_ws = PolymarketCLOBWebSocket()
    # ws is None — should warn and return without error
    await clob_ws.subscribe_assets(["token_up"])  # Should not raise


@pytest.mark.asyncio
async def test_subscribe_assets_noop_when_empty_list() -> None:
    """subscribe_assets does nothing when token_ids is empty."""
    clob_ws = PolymarketCLOBWebSocket()
    mock_ws = AsyncMock()
    mock_ws.closed = False
    clob_ws.ws = mock_ws

    await clob_ws.subscribe_assets([])

    mock_ws.send_str.assert_not_called()
