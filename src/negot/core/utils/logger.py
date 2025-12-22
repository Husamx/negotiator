"""
Application logging configuration.

This module centralises logging configuration to ensure consistent
formatting across services. Import and call ``configure_logging()`` at
application startup to configure the root logger.
"""
import logging


def configure_logging(level: str = "INFO") -> None:
    """Configure the root logger with a simple format.

    :param level: Logging level (e.g., 'DEBUG', 'INFO').
    """
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )