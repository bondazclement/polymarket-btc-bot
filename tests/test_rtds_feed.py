"""Tests for src/feeds/polymarket_rtds.py"""

import pytest

from src.feeds.polymarket_rtds import PolymarketRTDS


@pytest.fixture
def rtds() -> PolymarketRTDS:
    """Fixture returning a fresh PolymarketRTDS instance."""
    return PolymarketRTDS()


def test_handle_update_event_sets_current_price(rtds: PolymarketRTDS) -> None:
    """RTDS 'update' event with payload.value updates current_price."""
    msg = {
        "topic": "crypto_prices_chainlink",
        "type": "update",
        "timestamp": 1710000000000,
        "payload": {
            "symbol": "btc/usd",
            "value": 67234.50,
            "timestamp": 1710000000000,
        },
    }
    rtds._handle_message(msg)
    assert rtds.get_chainlink_price() == pytest.approx(67234.50)


def test_handle_unknown_type_does_not_crash(rtds: PolymarketRTDS) -> None:
    """Unknown event types are silently ignored."""
    msg = {"topic": "crypto_prices_chainlink", "type": "ping", "payload": {}}
    rtds._handle_message(msg)  # Should not raise
    assert rtds.get_chainlink_price() is None


def test_handle_wrong_topic_does_not_update_price(rtds: PolymarketRTDS) -> None:
    """Messages from other topics do not update current_price."""
    msg = {
        "topic": "equity_prices",
        "type": "update",
        "payload": {"symbol": "aapl", "value": 150.0},
    }
    rtds._handle_message(msg)
    assert rtds.get_chainlink_price() is None


def test_handle_payload_value_is_string(rtds: PolymarketRTDS) -> None:
    """payload.value as a string is correctly cast to float."""
    msg = {
        "topic": "crypto_prices_chainlink",
        "type": "update",
        "timestamp": 1710000000000,
        "payload": {"symbol": "btc/usd", "value": "87654.32"},
    }
    rtds._handle_message(msg)
    assert rtds.get_chainlink_price() == pytest.approx(87654.32)


def test_set_price_to_beat(rtds: PolymarketRTDS) -> None:
    """set_price_to_beat stores and exposes the opening price."""
    rtds.set_price_to_beat(87000.0)
    assert rtds.get_price_to_beat() == pytest.approx(87000.0)


def test_price_to_beat_starts_none(rtds: PolymarketRTDS) -> None:
    """price_to_beat is None before any window starts."""
    assert rtds.get_price_to_beat() is None


def test_current_price_starts_none(rtds: PolymarketRTDS) -> None:
    """current_price is None before any message is received."""
    assert rtds.get_chainlink_price() is None


def test_price_to_beat_independent_of_current_price(rtds: PolymarketRTDS) -> None:
    """price_to_beat and current_price are independent attributes."""
    msg = {
        "topic": "crypto_prices_chainlink",
        "type": "update",
        "timestamp": 1710000000000,
        "payload": {"symbol": "btc/usd", "value": 70000.0},
    }
    rtds._handle_message(msg)
    rtds.set_price_to_beat(69500.0)

    assert rtds.get_chainlink_price() == pytest.approx(70000.0)
    assert rtds.get_price_to_beat() == pytest.approx(69500.0)
