"""Structured logging setup for CLI, server and worker runs."""

import logging
import sys
import structlog


def _stderr_logger(*args):
    # Click/pytest replace and close their captured streams after each invocation.
    # Resolve the active stream on each log call, rather than caching a closed one.
    return structlog.PrintLogger(file=sys.stderr)


def _json_requested() -> bool:
    from caf_common.settings import get_settings

    return get_settings().app.env == "production"


def setup_logging(level: str = "INFO", json: bool | None = None) -> None:
    """Console output for people; JSON lines in production unless `json` says otherwise.

    JSON mode also routes standard-library records (uvicorn, SQLAlchemy, the worker) through the
    same renderer so every line carries the bound `request_id`.
    """
    use_json = _json_requested() if json is None else json
    log_level = getattr(logging, level.upper(), logging.INFO)
    timestamp = (
        structlog.processors.TimeStamper(fmt="iso", utc=True)
        if use_json
        else structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S", utc=False)
    )
    shared = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        timestamp,
    ]
    renderer = structlog.processors.JSONRenderer() if use_json else structlog.dev.ConsoleRenderer()

    structlog.configure(
        processors=[
            *shared,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info if use_json else structlog.dev.set_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        context_class=dict,
        logger_factory=_stderr_logger,
        cache_logger_on_first_use=False,
    )
    if use_json:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(
            structlog.stdlib.ProcessorFormatter(
                foreign_pre_chain=[*shared, structlog.stdlib.add_logger_name],
                processors=[
                    structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                    structlog.processors.format_exc_info,
                    renderer,
                ],
            )
        )
        root = logging.getLogger()
        root.handlers = [handler]
        root.setLevel(log_level)


def get_logger(name: str | None = None) -> structlog.BoundLogger:
    return structlog.get_logger(name)
