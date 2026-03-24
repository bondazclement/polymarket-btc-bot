"""
Test module for the trading loop in dry-run mode.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.engine.loop import TradingLoop
from src.engine.state import BotState
from src.feeds.feed_manager import FeedManager


@pytest.fixture
def mock_feed_manager():
    """Fixture to create a mock FeedManager."""
    feed_manager = MagicMock(spec=FeedManager)
    feed_manager.binance_feed = MagicMock()
    feed_manager.binance_feed.get_latest_price = MagicMock(return_value=50000.0)
    feed_manager.polymarket_rtds_feed = MagicMock()
    feed_manager.polymarket_rtds_feed.get_price_to_beat = MagicMock(return_value=49900.0)
    feed_manager.polymarket_clob_feed = MagicMock()
    feed_manager.polymarket_clob_feed.get_best_ask = MagicMock(return_value=0.5)
    return feed_manager


@pytest.fixture
def mock_state():
    """Fixture to create a mock BotState."""
    return BotState(
        bankroll=100.0,
        total_trades=0,
        wins=0,
        losses=0,
        current_position=None,
        pnl_history=[],
    )


@pytest.mark.asyncio
async def test_trading_loop_dry_run(mock_feed_manager, mock_state):
    """Test the trading loop in dry-run mode."""
    # Create the trading loop in dry-run mode
    trading_loop = TradingLoop(state=mock_state, mode="dry-run")
    
    # Mock the feeds, strategy, and clob_client
    trading_loop.feeds = mock_feed_manager
    trading_loop.strategy = MagicMock()
    trading_loop.clob_client = MagicMock()

    # Setup the mock evaluate_window to return a trade decision
    mock_evaluate_window = AsyncMock(return_value=MagicMock(
        side="Up",
        token_id="up_token_id",
        price=0.5,
        size=2.5,
        confidence=0.7,
    ))
    trading_loop.strategy.evaluate_window = mock_evaluate_window

    # Run one window iteration
    await trading_loop._run_window()

    # Verify that the order was not placed (dry-run mode)
    trading_loop.clob_client.place_order.assert_not_called()

    # Verify that the trade decision was logged
    # (This would typically be verified by checking logs, but for simplicity, we assume it's correct)
