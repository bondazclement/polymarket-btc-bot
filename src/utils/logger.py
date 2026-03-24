"""
Logger module for the Polymarket BTC UpDown 5m trading bot.

This module configures structured JSON logging using structlog.
"""

import structlog
from datetime import datetime


def configure_logger(log_level: str = "INFO") -> None:
    """Configure the logger with JSON output and structured logging.

    Args:
        log_level: Log level (DEBUG, INFO, WARNING, ERROR).
    """
    processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.StackInfoRenderer(),
        structlog.dev.set_exc_info,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ]

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=False,
    )


def get_logger(name: str) -> structlog.BoundLogger:
    """Get a named logger instance.

    Args:
        name: Name of the logger (usually __name__).

    Returns:
        Configured logger instance.
    """
    return structlog.get_logger(name)
