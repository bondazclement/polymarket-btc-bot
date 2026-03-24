"""
Test module for the slug resolver functions.
"""

import pytest

from src.execution.slug_resolver import get_current_slug


def test_get_current_slug_known_timestamp():
    """Test get_current_slug with a known timestamp."""
    timestamp = 1710000000  # A known timestamp
    slug = get_current_slug(timestamp)
    window_start = timestamp - (timestamp % 300)
    expected_slug = f"btc-updown-5m-{window_start}"
    assert slug == expected_slug


def test_get_current_slug_multiple_of_300():
    """Test get_current_slug to ensure the timestamp is a multiple of 300."""
    timestamp = 1710000000
    slug = get_current_slug(timestamp)
    window_start = int(slug.split("-")[-1])
    assert window_start % 300 == 0


def test_get_current_slug_current_time():
    """Test get_current_slug with the current time."""
    import time

    current_time = int(time.time())
    slug = get_current_slug()
    window_start = int(slug.split("-")[-1])
    assert window_start <= current_time
    assert window_start + 300 > current_time
