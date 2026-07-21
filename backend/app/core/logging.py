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

    # Applied to log records that did NOT originate from structlog (e.g.
    # SQLAlchemy, uvicorn, passlib). Without this, those records render with no
    # timestamp / level / logger name, so they look nothing like our own logs.
    # It intentionally omits filter_by_level (handled by logger levels below)
    # and wrap_for_formatter (only for structlog-native records).
    foreign_pre_chain: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
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

    # Configure stdlib logging to use structlog's formatter, so EVERY log line —
    # ours and third-party — comes out in one consistent format.
    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=foreign_pre_chain,
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

    # Tame noisy third-party loggers so the important lines stand out:
    #   - passlib: raised to ERROR to hide the harmless "error reading bcrypt
    #     version" traceback (a cosmetic passlib + bcrypt 4.x incompatibility).
    #   - sqlalchemy.engine: INFO only when DB_ECHO is on; it then flows through
    #     this handler as single, consistently formatted lines (no duplicates).
    noisy_logger_levels = {
        "uvicorn.access": logging.WARNING,
        "uvicorn.error": logging.WARNING,
        "httpx": logging.WARNING,
        "httpcore": logging.WARNING,
        "passlib": logging.ERROR,
        "sqlalchemy.engine": logging.INFO if settings.db_echo else logging.WARNING,
    }
    for logger_name, level in noisy_logger_levels.items():
        logging.getLogger(logger_name).setLevel(level)


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Get a named structured logger.

    Args:
        name: Logger name, typically __name__ of the calling module.

    Returns:
        A bound structured logger instance.
    """
    return structlog.get_logger(name)  # type: ignore[no-any-return]
