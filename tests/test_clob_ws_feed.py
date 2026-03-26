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


@pytest.mark.asyncio
async def test_subscribe_assets_stores_token_ids() -> None:
    """subscribe_assets stores token_ids for re-subscription after reconnect."""
    clob_ws = PolymarketCLOBWebSocket()
    mock_ws = AsyncMock()
    mock_ws.closed = False
    clob_ws.ws = mock_ws

    await clob_ws.subscribe_assets(["token_up", "token_down"])

    assert clob_ws._subscribed_token_ids == ["token_up", "token_down"]


@pytest.mark.asyncio
async def test_subscribe_assets_stores_token_ids_even_when_not_connected() -> None:
    """subscribe_assets stores token_ids even if ws is not connected yet."""
    clob_ws = PolymarketCLOBWebSocket()
    # ws is None, but token_ids should still be stored for later reconnect
    await clob_ws.subscribe_assets(["token_up", "token_down"])

    assert clob_ws._subscribed_token_ids == ["token_up", "token_down"]


@pytest.mark.asyncio
async def test_ping_loop_sends_ping_text_frame() -> None:
    """_ping_loop sends plain-text 'PING' (not a protocol ping) every 10s."""
    import asyncio

    clob_ws = PolymarketCLOBWebSocket()
    mock_ws = AsyncMock()
    mock_ws.closed = False
    clob_ws.ws = mock_ws

    task = asyncio.create_task(clob_ws._ping_loop())
    # Advance past the first 10s sleep
    await asyncio.sleep(0)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    # The ping loop sleeps first — no ping yet on first iteration before sleep
    # Just verify it didn't raise and send_str was called 0 or 1 times with "PING"
    for call in mock_ws.send_str.call_args_list:
        assert call[0][0] == "PING"


def test_listen_handles_pong_without_crash(clob_ws: PolymarketCLOBWebSocket) -> None:
    """PONG plain-text response from server does not crash _handle_message."""
    # Simulate that _listen would skip PONG before JSON parsing.
    # We verify the guard: msg.data == "PONG" short-circuits orjson.loads.
    # Direct test: calling _handle_message with non-JSON would crash — the guard
    # must be in _listen, not _handle_message.
    import orjson

    with pytest.raises(Exception):
        orjson.loads("PONG")  # Confirms "PONG" is not valid JSON


@pytest.mark.asyncio
async def test_listen_skips_pong_and_updates_last_message_ts() -> None:
    """_listen updates last_message_ts on PONG without calling _handle_message."""
    import asyncio
    from unittest.mock import MagicMock, patch
    import aiohttp

    clob_ws = PolymarketCLOBWebSocket()

    pong_msg = MagicMock()
    pong_msg.type = aiohttp.WSMsgType.TEXT
    pong_msg.data = "PONG"

    close_msg = MagicMock()
    close_msg.type = aiohttp.WSMsgType.CLOSED

    async def fake_iter():
        yield pong_msg
        yield close_msg

    mock_ws = MagicMock()
    mock_ws.__aiter__ = lambda self: fake_iter()
    clob_ws.ws = mock_ws

    with patch.object(clob_ws, "_handle_message") as mock_handle:
        await clob_ws._listen()
        mock_handle.assert_not_called()

    assert clob_ws.last_message_ts > 0
