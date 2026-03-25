"""
Test module for taker_selective strategy logging.
"""

import time
from collections import deque

import pytest
from unittest.mock import MagicMock, patch, AsyncMock

from src.engine.state import BotState
from src.feeds.binance_ws import Tick
from src.feeds.feed_manager import FeedManager
from src.signal.scorer import SignalScorer
from src.strategy.taker_selective import TakerSelectiveStrategy


@pytest.fixture
def mock_feeds() -> MagicMock:
    """Fixture to create a mock FeedManager."""
    feeds = MagicMock(spec=FeedManager)
    feeds.binance_feed = MagicMock()
    feeds.binance_feed.get_latest_price = MagicMock(return_value=0.0)
    feeds.polymarket_rtds_feed = MagicMock()
    feeds.polymarket_rtds_feed.get_price_to_beat = MagicMock(return_value=None)
    feeds.polymarket_clob_feed = MagicMock()
    return feeds


@pytest.fixture
def state() -> BotState:
    """Fixture to create a BotState."""
    return BotState(
        bankroll=100.0,
        total_trades=0,
        wins=0,
        losses=0,
        current_position=None,
        pnl_history=[],
    )


@pytest.mark.asyncio
async def test_logs_skip_on_missing_price(mock_feeds: MagicMock, state: BotState) -> None:
    """Strategy should log skip reason when prices are missing."""
    strategy = TakerSelectiveStrategy()
    scorer = SignalScorer()

    with patch("src.strategy.taker_selective.logger") as mock_logger:
        result = await strategy.evaluate_window(
            feeds=mock_feeds,
            signal_scorer=scorer,
            state=state,
        )

    assert result is None
    mock_logger.info.assert_called()
    call_args = mock_logger.info.call_args
    assert "Skip" in call_args[0][0]


@pytest.mark.asyncio
async def test_logs_skip_on_insufficient_ticks(mock_feeds: MagicMock, state: BotState) -> None:
    """Strategy should log skip reason when insufficient ticks."""
    mock_feeds.binance_feed.get_latest_price.return_value = 87000.0
    mock_feeds.polymarket_rtds_feed.get_price_to_beat.return_value = 86900.0
    now_ms = int(time.time() * 1000)
    ticks: deque[Tick] = deque(
        [Tick(price=87000.0, quantity=0.01, timestamp=now_ms - i * 200, is_buyer_maker=False) for i in range(5)],
        maxlen=600,
    )
    mock_feeds.binance_feed.get_price_buffer.return_value = ticks

    strategy = TakerSelectiveStrategy()
    scorer = SignalScorer()

    with patch("src.strategy.taker_selective.logger") as mock_logger:
        result = await strategy.evaluate_window(
            feeds=mock_feeds,
            signal_scorer=scorer,
            state=state,
        )

    assert result is None
    mock_logger.info.assert_called()
    # Should mention insufficient ticks
    logged_messages = [call[0][0] for call in mock_logger.info.call_args_list]
    assert any("insufficient ticks" in msg for msg in logged_messages)
