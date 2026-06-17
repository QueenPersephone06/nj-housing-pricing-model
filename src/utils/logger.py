"""Centralized logging configuration.

Usage:
    from src.utils.logger import get_logger
    log = get_logger(__name__)
    log.info("hello")
"""
from __future__ import annotations

import logging
import logging.handlers
import sys
from pathlib import Path

_LOG_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

_INITIALISED = False


def _init_root_logger(log_dir: str | Path = "logs") -> None:
    global _INITIALISED
    if _INITIALISED:
        return

    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(logging.INFO)

    # Console handler
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(logging.Formatter(_LOG_FORMAT, _DATE_FORMAT))
    root.addHandler(ch)

    # Rotating file handler
    fh = logging.handlers.RotatingFileHandler(
        log_path / "pipeline.log",
        maxBytes=5_000_000,
        backupCount=3,
        encoding="utf-8",
    )
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(_LOG_FORMAT, _DATE_FORMAT))
    root.addHandler(fh)

    _INITIALISED = True


def get_logger(name: str, log_dir: str | Path = "logs") -> logging.Logger:
    _init_root_logger(log_dir)
    return logging.getLogger(name)
