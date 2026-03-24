"""
Test module for the trading filters.
"""

import pytest

from src.engine.state import BotState
from src.signal.scorer import SignalResult
from src.strategy.filters import should_trade


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


def test_should_trade_signal_skip(mock_state):
    """Test should_trade with a SKIP signal."""
    signal = SignalResult(direction="SKIP", confidence=0.7, suggested_side=None)
    best_ask = 0.5
    should_execute, reason = should_trade(signal, best_ask, mock_state)
    assert not should_execute
    assert reason == "Signal direction is SKIP"


def test_should_trade_best_ask_too_high(mock_state):
    """Test should_trade with a best ask price above the maximum allowed price."""
    signal = SignalResult(direction="UP", confidence=0.7, suggested_side="Up")
    best_ask = 0.7  # Above MAX_TOKEN_PRICE (0.60)
    should_execute, reason = should_trade(signal, best_ask, mock_state)
    assert not should_execute
    assert reason == f"Best ask price {best_ask} exceeds maximum allowed price 0.6"


def test_should_trade_low_confidence(mock_state):
    """Test should_trade with a signal confidence below the threshold."""
    signal = SignalResult(direction="UP", confidence=0.5, suggested_side="Up")
    best_ask = 0.5
    should_execute, reason = should_trade(signal, best_ask, mock_state)
    assert not should_execute
    assert reason == "Signal confidence 0.5 is below the required threshold of 0.6"


def test_should_trade_stop_loss_hit(mock_state):
    """Test should_trade with a stop loss hit."""
    mock_state.current_position = 0.8
    signal = SignalResult(direction="UP", confidence=0.7, suggested_side="Up")
    best_ask = 0.5
    should_execute, reason = should_trade(signal, best_ask, mock_state)
    assert not should_execute
    assert reason == "There is already an open position"


def test_should_trade_open_position(mock_state):
    """Test should_trade with an open position."""
    mock_state.current_position = 1.0
    signal = SignalResult(direction="UP", confidence=0.7, suggested_side="Up")
    best_ask = 0.5
    should_execute, reason = should_trade(signal, best_ask, mock_state)
    assert not should_execute
    assert reason == "There is already an open position"


def test_should_trade_all_conditions_met(mock_state):
    """Test should_trade with all conditions met."""
    signal = SignalResult(direction="UP", confidence=0.7, suggested_side="Up")
    best_ask = 0.5
    mock_state.current_position = None
    should_execute, reason = should_trade(signal, best_ask, mock_state)
    assert should_execute
    assert reason == "All conditions are met"
