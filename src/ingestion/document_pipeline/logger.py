"""
logger.py — Structured logging for the Document Extraction Pipeline.

Emits both:
  - Human-readable console output (colourised)
  - JSON-structured file log  (logs/document_pipeline.log)

Standard event tokens: START · DOWNLOAD · PARSE · SAVE · FAIL · RETRY · COMPLETE
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ─────────────────────────────────────────────────────────────────────────────
# ANSI colour helpers (console only)
# ─────────────────────────────────────────────────────────────────────────────
_RESET  = "\033[0m"
_BOLD   = "\033[1m"
_RED    = "\033[91m"
_YELLOW = "\033[93m"
_GREEN  = "\033[92m"
_CYAN   = "\033[96m"
_DIM    = "\033[2m"

_LEVEL_COLOURS = {
    "DEBUG":    _DIM,
    "INFO":     _GREEN,
    "WARNING":  _YELLOW,
    "ERROR":    _RED,
    "CRITICAL": _BOLD + _RED,
}


class _ColourConsoleFormatter(logging.Formatter):
    """Colourised, human-readable formatter for stderr."""

    def format(self, record: logging.LogRecord) -> str:
        colour = _LEVEL_COLOURS.get(record.levelname, "")
        ts = datetime.now().strftime("%H:%M:%S")
        event = getattr(record, "event", "")
        event_str = f" [{_CYAN}{event}{_RESET}]" if event else ""
        msg = super().format(record)
        return (
            f"{_DIM}{ts}{_RESET} "
            f"{colour}{record.levelname:<8}{_RESET}"
            f"{event_str} {msg}"
        )


class _JsonFileFormatter(logging.Formatter):
    """JSON-line formatter for the log file (machine-readable)."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts":      datetime.now(timezone.utc).isoformat(),
            "level":   record.levelname,
            "event":   getattr(record, "event", ""),
            "logger":  record.name,
            "message": record.getMessage(),
        }
        # Copy any extra structured fields attached to the record
        for key in ("url", "file", "parser", "error", "duration_s", "retry"):
            val = getattr(record, key, None)
            if val is not None:
                payload[key] = val

        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)

        return json.dumps(payload, ensure_ascii=False)


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def setup_pipeline_logger(log_dir: Path, name: str = "doc_pipeline") -> logging.Logger:
    """
    Configure and return the pipeline logger.
    Call once at startup.
    """
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "document_pipeline.log"

    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    if logger.handlers:
        return logger  # already initialised (e.g., in tests)

    # ── File handler (JSON, DEBUG level) ──────────────────────────────────
    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(_JsonFileFormatter())
    logger.addHandler(fh)

    # ── Console handler (colourised, INFO level) ───────────────────────────
    ch = logging.StreamHandler(sys.stderr)
    ch.setLevel(logging.INFO)
    ch.setFormatter(_ColourConsoleFormatter())
    logger.addHandler(ch)

    return logger


def get_logger(name: str = "doc_pipeline") -> logging.Logger:
    """Return the already-configured pipeline logger (or create a plain one)."""
    return logging.getLogger(name)


# ─────────────────────────────────────────────────────────────────────────────
# Convenience event helpers
# ─────────────────────────────────────────────────────────────────────────────

def log_event(
    logger: logging.Logger,
    event: str,
    message: str,
    level: str = "INFO",
    **extra: Any,
) -> None:
    """
    Emit a structured log line with a named event token.

    Example::

        log_event(logger, "DOWNLOAD", "Fetched PDF", url="https://...", duration_s=1.2)
    """
    lvl = getattr(logging, level.upper(), logging.INFO)
    logger.log(lvl, message, extra={"event": event, **extra})
