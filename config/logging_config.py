"""
Market Insight Engine – Structured Logging Configuration
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Call `configure_logging()` once at application startup.
All subsequent `logging.getLogger(name)` calls inherit this config.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Literal

from rich.console import Console
from rich.logging import RichHandler

_console = Console(stderr=True)


def configure_logging(
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO",
    log_dir: Path | None = None,
) -> None:
    """
    Configure the root logger with:
    - RichHandler  → pretty console output (human-readable, colorised)
    - FileHandler  → JSON-structured lines written to log_dir/mie.log
    """
    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()

    # ── Console handler (via Rich) ──────────────────────────────────── #
    console_handler = RichHandler(
        console=_console,
        show_time=True,
        show_path=True,
        rich_tracebacks=True,
        tracebacks_show_locals=False,
    )
    console_handler.setLevel(level)
    console_handler.setFormatter(logging.Formatter("%(message)s"))
    root.addHandler(console_handler)

    # ── File handler (plain text with timestamp; JSON upgrade in Phase 7) #
    if log_dir is not None:
        log_dir.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_dir / "mie.log", encoding="utf-8")
        file_handler.setLevel("DEBUG")  # capture everything to file
        file_fmt = logging.Formatter(
            fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        )
        file_handler.setFormatter(file_fmt)
        root.addHandler(file_handler)

    # Silence noisy third-party loggers
    for noisy in ("urllib3", "httpx", "httpcore", "akshare"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
