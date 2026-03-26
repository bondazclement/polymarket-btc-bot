"""
Configuration module for the Polymarket BTC UpDown 5m trading bot.

This module loads environment variables and defines constants used across the bot.
"""

from dataclasses import dataclass
from os import getenv
from pathlib import Path

from dotenv import load_dotenv


load_dotenv(Path(__file__).resolve().parent.parent / ".env")


@dataclass(slots=True, frozen=True)
class Config:
    """Configuration dataclass for the trading bot.

    Attributes:
        POLYMARKET_PRIVATE_KEY: Private key for the EOA on Polygon.
        POLYMARKET_FUNDER: Address of the proxy wallet on Polymarket.
        POLYMARKET_API_KEY: API key for Polymarket L2 credentials.
        POLYMARKET_API_SECRET: API secret for Polymarket L2 credentials.
        POLYMARKET_PASSPHRASE: Passphrase for Polymarket L2 credentials.
        POLYGON_RPC_URL: RPC URL for Polygon network.
        BINANCE_WS_URL: WebSocket URL for Binance BTC/USDT trades.
        POLYMARKET_CLOB_URL: REST URL for Polymarket CLOB.
        POLYMARKET_RTDS_URL: WebSocket URL for Polymarket RTDS (Chainlink data).
        DELTA_MIN: Minimum delta threshold for trading.
        EDGE_BUFFER: Buffer for edge calculation.
        MAX_TOKEN_PRICE: Maximum token price for trading.
        KELLY_FRACTION: Fraction of Kelly criterion to use for sizing.
        STOP_LOSS_PCT: Stop loss percentage.
    """

    POLYMARKET_PRIVATE_KEY: str
    POLYMARKET_FUNDER: str
    POLYMARKET_API_KEY: str
    POLYMARKET_API_SECRET: str
    POLYMARKET_PASSPHRASE: str
    POLYGON_RPC_URL: str
    BINANCE_WS_URL: str = "wss://stream.binance.com:9443/ws/btcusdt@aggTrade"
    POLYMARKET_CLOB_URL: str = "https://clob.polymarket.com"
    POLYMARKET_RTDS_URL: str = "wss://ws-live-data.polymarket.com"
    DELTA_MIN: float = 0.0003
    EDGE_BUFFER: float = 0.05
    MAX_TOKEN_PRICE: float = 0.60
    POLYMARKET_CLOB_WS_URL: str = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
    KELLY_FRACTION: float = 0.25
    STOP_LOSS_PCT: float = 0.20
    BOOTSTRAP_WIN_RATE: float = 0.65
    RESOLUTION_WAIT_SECONDS: float = 15.0


# Load configuration from environment variables
CONFIG = Config(
    POLYMARKET_PRIVATE_KEY=getenv("POLYMARKET_PRIVATE_KEY", ""),
    POLYMARKET_FUNDER=getenv("POLYMARKET_FUNDER", ""),
    POLYMARKET_API_KEY=getenv("POLYMARKET_API_KEY", ""),
    POLYMARKET_API_SECRET=getenv("POLYMARKET_API_SECRET", ""),
    POLYMARKET_PASSPHRASE=getenv("POLYMARKET_PASSPHRASE", ""),
    POLYGON_RPC_URL=getenv("POLYGON_RPC_URL", ""),
)
