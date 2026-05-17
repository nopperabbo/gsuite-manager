from __future__ import annotations

import logging
import sys
from datetime import datetime
from typing import Any

import structlog
from rich.console import Console
from rich.logging import RichHandler

from gsm.core.config import Settings

LEGACY_PREFIXES: dict[str, str] = {
    "ok": "[+]",
    "fail": "[-]",
    "info": "[*]",
    "warn": "[!]",
}

_console = Console(stderr=False)


def configure_logging(settings: Settings) -> None:
    level = logging.getLevelName(settings.log_level)

    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=False),
        structlog.processors.StackInfoRenderer(),
    ]

    if settings.log_format == "json":
        renderer: Any = structlog.processors.JSONRenderer()
        handler: logging.Handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter("%(message)s"))
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=True)
        handler = RichHandler(
            console=_console,
            show_path=False,
            show_time=False,
            markup=False,
            rich_tracebacks=True,
        )

    structlog.configure(
        processors=[*shared_processors, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)


def get_logger(name: str | None = None) -> Any:
    return structlog.get_logger(name) if name else structlog.get_logger()


def legacy_log(status: str, message: str) -> None:
    # Mirrors legacy gsuite_cloudflare_bot.py output format so users can
    # recognize progress lines without retraining their eyes.
    prefix = LEGACY_PREFIXES.get(status, "[?]")
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"{timestamp} {prefix} {message}", flush=True)

    log = get_logger("gsm.legacy")
    if status == "ok":
        log.info(message, legacy_status=status)
    elif status == "fail":
        log.error(message, legacy_status=status)
    elif status == "warn":
        log.warning(message, legacy_status=status)
    else:
        log.info(message, legacy_status=status)
