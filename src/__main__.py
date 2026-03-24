"""
Main entry point for the Polymarket BTC UpDown 5m trading bot.

This module parses command-line arguments, initializes the bot,
and starts the main trading loop.
"""

import argparse
import asyncio

import uvloop

from src.config import CONFIG
from src.engine.loop import TradingLoop
from src.engine.state import BotState
from src.utils.logger import configure_logger


async def main() -> None:
    """Main function to run the trading bot."""
    parser = argparse.ArgumentParser(description="Polymarket BTC UpDown 5m Trading Bot")
    parser.add_argument(
        "--mode",
        type=str,
        choices=["dry-run", "safe"],
        default="dry-run",
        help="Trading mode (dry-run or safe)",
    )
    parser.add_argument(
        "--max-trades",
        type=int,
        default=100,
        help="Maximum number of trades to execute",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Log level",
    )

    args = parser.parse_args()

    # Configure logging
    configure_logger(log_level=args.log_level)

    # Initialize bot state
    state = BotState(
        bankroll=100.0,
        total_trades=0,
        wins=0,
        losses=0,
        current_position=None,
        pnl_history=[],
    )

    # Create and run the trading loop
    trading_loop = TradingLoop(state=state, mode=args.mode)
    await trading_loop.run()


if __name__ == "__main__":
    uvloop.run(main())
