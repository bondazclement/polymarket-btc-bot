"""
Test module for the order builder functions.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from py_clob_client.client import ClobClient
from py_clob_client import OrderArgs

from src.execution.order_builder import build_order


@pytest.fixture
def mock_client():
    """Fixture to create a mock ClobClient."""
    client = MagicMock(spec=ClobClient)
    client.get_fee_rate_bps = AsyncMock(return_value=100)  # Mock fee rate
    client.sign_order = AsyncMock(return_value=OrderArgs(
        token_id="test_token",
        side="Up",
        price=0.5,
        size=2.5,
        fee_rate_bps=100,
    ))
    return client


@pytest.mark.asyncio
async def test_build_order_success(mock_client):
    """Test build_order with a successful order build."""
    token_id = "test_token"
    side = "Up"
    price = 0.5
    size = 2.5

    order = await build_order(mock_client, token_id, side, price, size)

    assert order is not None
    assert order.token_id == token_id
    assert order.side == side
    assert order.price == price
    assert order.size == size
    assert order.fee_rate_bps == 100


@pytest.mark.asyncio
async def test_build_order_failure(mock_client):
    """Test build_order with a failed order build."""
    mock_client.get_fee_rate_bps.side_effect = Exception("Failed to get fee rate")

    token_id = "test_token"
    side = "Up"
    price = 0.5
    size = 2.5

    order = await build_order(mock_client, token_id, side, price, size)

    assert order is None
