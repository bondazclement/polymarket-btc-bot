"""
Test module for the order builder functions.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.execution.order_builder import build_and_post_order


@pytest.fixture
def mock_polymarket_client():
    """Fixture to create a mock PolymarketClient."""
    client = MagicMock()
    client.client = MagicMock()
    client.client.create_order = MagicMock(return_value={"signed": True})
    client.client.post_order = MagicMock(return_value={"orderID": "test123"})
    return client


@pytest.mark.asyncio
async def test_build_and_post_order_success(mock_polymarket_client):
    """Test build_and_post_order with a successful order."""
    result = await build_and_post_order(
        mock_polymarket_client, "test_token", "Up", 0.5, 2.5
    )
    assert result is True


@pytest.mark.asyncio
async def test_build_and_post_order_failure(mock_polymarket_client):
    """Test build_and_post_order with a failed order."""
    mock_polymarket_client.client.create_order.side_effect = Exception("API error")

    result = await build_and_post_order(
        mock_polymarket_client, "test_token", "Up", 0.5, 2.5
    )
    assert result is False
