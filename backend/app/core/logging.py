"""Structured logging configuration using structlog.

Design Decisions:
    - JSON output in production for log aggregation (ELK, Datadog, etc.).
    - Human-readable colored output in development for developer experience.
    - Request ID correlation is added via middleware (future step).
    - structlog processors handle timestamping, log level, and caller info.

Why structlog over stdlib logging?
    - Structured (key-value) logs are searchable and parseable.
    - Immutable context binding avoids global state issues.
    - Processors pipeline is composable and testable.
"""

import logging
import sys

import structlog

from app.config import get_settings


def setup_logging() -> None:
    """Configure structured logging for the application.

    In production: JSON lines format for machine parsing.
    In development: Colored, human-readable console output.
    """
    settings = get_settings()
    log_level = settings.app_log_level.upper()

    # Shared processors for both dev and prod
    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]

    if settings.is_production:
        # Production: JSON output for log aggregation
        renderer: structlog.types.Processor = structlog.processors.JSONRenderer()
    else:
        # Development: colored, human-readable output
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # Configure stdlib logging to use structlog's formatter
    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(log_level)

    # Silence noisy third-party loggers
    for logger_name in ("uvicorn.access", "uvicorn.error", "httpx", "httpcore"):
        logging.getLogger(logger_name).setLevel(logging.WARNING)


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Get a named structured logger.

    Args:
        name: Logger name, typically __name__ of the calling module.

    Returns:
        A bound structured logger instance.
    """
    return structlog.get_logger(name)  # type: ignore[no-any-return]
