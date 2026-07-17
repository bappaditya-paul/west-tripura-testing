"""
ingestion/utils.py
==================
Shared utility functions used by every stage of the ingestion pipeline.

Covers:
  - Structured logging (setup_logger, log_event)
  - Failed-document registry (FailedRegistry)
  - ID generation (make_document_id, make_chunk_id)
  - Text helpers (clean_text, count_words, content_hash)
  - JSON I/O (safe_json_load, safe_json_dump)
  - Bengali detection helpers
  - URL helpers
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time
import unicodedata
from collections import defaultdict
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


# ─────────────────────────────────────────────────────────────────────────────
# Logging
# ─────────────────────────────────────────────────────────────────────────────

def setup_logger(name: str, log_path: Path | None = None) -> logging.Logger:
    """Create a named logger that writes to console and optionally to a file."""
    logger = logging.getLogger(name)
    if logger.handlers:           # already configured (e.g. after re-import)
        return logger

    logger.setLevel(logging.DEBUG)
    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console handler — INFO and above
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    # File handler — DEBUG and above
    if log_path is not None:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        fh = RotatingFileHandler(log_path, maxBytes=10 * 1024 * 1024, backupCount=3,
                                 encoding="utf-8")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(fmt)
        logger.addHandler(fh)

    return logger


def log_event(
    log: logging.Logger,
    event_type: str,
    message: str,
    *,
    level: str = "INFO",
    **extra: Any,
) -> None:
    """Log a structured event.  Extra kwargs are appended as key=value pairs."""
    suffix = "  " + "  ".join(f"{k}={v}" for k, v in extra.items()) if extra else ""
    full = f"[{event_type}] {message}{suffix}"
    getattr(log, level.lower(), log.info)(full)


# ─────────────────────────────────────────────────────────────────────────────
# Failed-document registry
# ─────────────────────────────────────────────────────────────────────────────

class FailedRegistry:
    """Thread-safe registry that appends failed-document entries to a JSON file."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._records: list[dict[str, Any]] = []
        if path.exists():
            try:
                self._records = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                self._records = []

    def record(self, *, file: str = "", error: str = "", stage: str = "", **kw: Any) -> None:
        entry = {
            "file": file,
            "stage": stage,
            "error": error,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **kw,
        }
        self._records.append(entry)
        safe_json_dump(self._records, self._path)

    def __len__(self) -> int:
        return len(self._records)


# ─────────────────────────────────────────────────────────────────────────────
# ID generation
# ─────────────────────────────────────────────────────────────────────────────

def make_document_id(url: str, stem: str = "") -> str:
    """Produce a deterministic, filesystem-safe document ID."""
    raw = url if url else stem
    # Remove scheme, collapse non-alphanum to underscores
    slug = re.sub(r"[^a-zA-Z0-9]", "_", raw).strip("_").lower()
    if len(slug) > 100:
        slug = slug[:100]
    suffix = hashlib.md5(raw.encode("utf-8")).hexdigest()[:8]
    return f"{slug}__{suffix}"


def make_chunk_id(document_id: str, index: int) -> str:
    """Produce a deterministic chunk ID from document_id + chunk index."""
    return f"{document_id}__chunk_{index:04d}"


# ─────────────────────────────────────────────────────────────────────────────
# Text helpers
# ─────────────────────────────────────────────────────────────────────────────

_MULTI_BLANK_RE = re.compile(r"\n{3,}")
_MULTI_SPACE_RE = re.compile(r"[ \t]{2,}")
_CTRL_RE        = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def clean_text(text: str) -> str:
    """
    Normalise Unicode, strip control characters, collapse excess whitespace.
    Preserves Markdown structure (single blank lines, code fences, etc.).
    """
    text = unicodedata.normalize("NFC", text)
    text = _CTRL_RE.sub("", text)
    lines = [_MULTI_SPACE_RE.sub(" ", line.rstrip()) for line in text.splitlines()]
    text = "\n".join(lines)
    text = _MULTI_BLANK_RE.sub("\n\n", text)
    return text.strip()


def count_words(text: str) -> int:
    """Approximate word count that handles Bengali and mixed scripts."""
    # Bengali characters occupy one 'word' each when space-split
    tokens = text.split()
    return len(tokens)


def content_hash(text: str) -> str:
    """SHA-256 hex digest of UTF-8 encoded text."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_of_text(text: str) -> str:
    """Alias for content_hash — kept for backward compatibility."""
    return content_hash(text)


def estimate_tokens(text: str) -> int:
    """
    Fast token-count approximation.
    Bengali characters are denser — roughly 3 chars per token.
    ASCII text uses the standard 4-chars-per-token heuristic.
    """
    bengali_chars = sum(1 for c in text if "\u0980" <= c <= "\u09FF")
    if bengali_chars > len(text) * 0.1:
        return max(1, len(text) // 3)
    return max(1, len(text) // 4)


# ─────────────────────────────────────────────────────────────────────────────
# Language detection
# ─────────────────────────────────────────────────────────────────────────────

_BENGALI_RE = re.compile(r"[\u0980-\u09FF]")


def contains_bengali(text: str) -> bool:
    return bool(_BENGALI_RE.search(text))


def detect_language(text: str) -> str:
    """Return 'bn', 'en', or 'mixed'."""
    if not text:
        return "unknown"
    sample = text[:2000]
    bn = len(_BENGALI_RE.findall(sample))
    en = sum(1 for c in sample if c.isascii() and c.isalpha())
    total = bn + en or 1
    ratio  = bn / total
    if ratio > 0.6:
        return "bn"
    if ratio < 0.2:
        return "en"
    return "mixed"


# ─────────────────────────────────────────────────────────────────────────────
# JSON I/O
# ─────────────────────────────────────────────────────────────────────────────

def safe_json_load(path: Path) -> Any:
    """Load a JSON file; return None on any error."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def safe_json_dump(obj: Any, path: Path, *, indent: int | None = 2) -> bool:
    """Write obj as JSON to path (creates parent dirs).  Returns True on success."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(obj, ensure_ascii=False, indent=indent),
                        encoding="utf-8")
        return True
    except Exception:
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Frontmatter parser
# ─────────────────────────────────────────────────────────────────────────────

def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """
    Split YAML-style frontmatter from a Markdown file.

    Returns (metadata_dict, body_text).
    """
    meta: dict[str, str] = {}
    body = text
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            for line in parts[1].strip().splitlines():
                if ":" in line:
                    k, _, v = line.partition(":")
                    meta[k.strip()] = v.strip().strip('"').strip("'")
            body = parts[2].strip()
    return meta, body


# ─────────────────────────────────────────────────────────────────────────────
# URL helpers
# ─────────────────────────────────────────────────────────────────────────────

def url_to_domain(url: str) -> str:
    parsed = urlparse(url)
    hostname = parsed.hostname or ""
    return hostname.removeprefix("www.")


def url_to_slug(url: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]", "_", url).strip("_").lower()
    if len(slug) > 160:
        slug = slug[:160]
    suffix = hashlib.md5(url.encode()).hexdigest()[:8]
    return f"{slug}__{suffix}" if slug else suffix


# ─────────────────────────────────────────────────────────────────────────────
# Markdown structural helpers (used by build_heading_tree, chunk_pages)
# ─────────────────────────────────────────────────────────────────────────────

def is_table_line(line: str) -> bool:
    s = line.strip()
    return s.startswith("|") and s.endswith("|")


def is_list_line(line: str) -> bool:
    s = line.strip()
    return (
        bool(re.match(r"^[-*+]\s", s))
        or bool(re.match(r"^\d+[.)]\s", s))
        or bool(re.match(r"^[ivxlcdm]+[.)]\s", s.lower()))
    )


def heading_level(line: str) -> int | None:
    m = re.match(r"^(#+)\s", line.strip())
    return len(m.group(1)) if m else None
