"""
utils.py — Shared utility functions for the Document Extraction Pipeline.

Covers:
  - URL → filename normalisation
  - SHA-256 hashing
  - Extension-based content-type detection
  - Failed-URL extraction from crawl.log
  - Language detection (heuristic for Bengali / English govt docs)
  - Word count
  - Safe JSON serialisation
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse, quote

from .config import (
    DOCX_EXTENSIONS,
    PDF_EXTENSIONS,
    SUPPORTED_EXTENSIONS,
    XLSX_EXTENSIONS,
)


# ─────────────────────────────────────────────────────────────────────────────
# URL helpers
# ─────────────────────────────────────────────────────────────────────────────

def url_to_stem(url: str) -> str:
    """
    Convert a URL to a safe filesystem stem (no extension).

    Example::

        url_to_stem("https://wptripura.nic.in/ADMISSIONFORM24.pdf")
        # → "ADMISSIONFORM24"
    """
    parsed = urlparse(url)
    raw = unquote(parsed.path)
    name = Path(raw).stem or "document"
    # Remove unsafe characters, collapse spaces/underscores
    name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    name = re.sub(r"[^\w\-]", "_", name)
    name = re.sub(r"_+", "_", name).strip("_")
    return name[:120] or "document"


def url_to_filename(url: str, suffix: str = "") -> str:
    """
    Build a unique filename for a URL.
    Appends first 8 chars of URL hash to avoid collisions.
    """
    stem = url_to_stem(url)
    url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
    return f"{stem}__{url_hash}{suffix}"


def normalize_url(url: str) -> str:
    """
    Percent-encode spaces and unsafe characters in the URL path.

    Govt URLs often contain literal spaces, e.g.:
      ``http://wptripura.nic.in/Fee _Structure.pdf``
    aiohttp / requests will reject these; we must encode them first.
    Already-encoded sequences (e.g. %20) are left untouched.
    """
    parsed = urlparse(url.strip())
    # quote() encodes spaces and unsafe chars but leaves already-encoded %XX alone
    safe_path = quote(parsed.path, safe='/:@!$&\'()*+,;=%-')
    # Rebuild URL with encoded path (keep query/fragment unchanged)
    return parsed._replace(path=safe_path).geturl()


def get_extension(url: str) -> str:
    """Return the lowercased extension of the URL path (e.g. '.pdf')."""
    parsed = urlparse(url)
    path = unquote(parsed.path)
    return Path(path).suffix.lower()


def get_content_type(url: str) -> str | None:
    """
    Map a URL extension to a content-type label.

    Returns 'pdf', 'docx', 'xlsx', or None (unsupported).
    """
    ext = get_extension(url)
    if ext in PDF_EXTENSIONS:
        return "pdf"
    if ext in DOCX_EXTENSIONS:
        return "docx"
    if ext in XLSX_EXTENSIONS:
        return "xlsx"
    return None


def is_supported(url: str) -> bool:
    """Return True if the URL points to a supported document type."""
    return get_extension(url) in SUPPORTED_EXTENSIONS


# ─────────────────────────────────────────────────────────────────────────────
# File hashing
# ─────────────────────────────────────────────────────────────────────────────

def sha256_of_bytes(data: bytes) -> str:
    """Return the hex SHA-256 digest of raw bytes."""
    return hashlib.sha256(data).hexdigest()


def sha256_of_file(path: Path) -> str:
    """Return the hex SHA-256 digest of a file (streaming, memory-safe)."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


# ─────────────────────────────────────────────────────────────────────────────
# Text analytics
# ─────────────────────────────────────────────────────────────────────────────

def count_words(text: str) -> int:
    """Simple whitespace-based word count."""
    return len(text.split())


# Bengali Unicode range: \u0980–\u09FF
_BENGALI_RE = re.compile(r"[\u0980-\u09FF]")

def detect_language(text: str) -> str:
    """
    Heuristic language detection for West Tripura govt docs.

    Returns 'bn' (Bengali), 'en' (English), or 'mixed'.
    """
    if not text:
        return "unknown"
    sample = text[:2000]
    bn_count = len(_BENGALI_RE.findall(sample))
    ascii_count = sum(1 for c in sample if c.isascii() and c.isalpha())
    total = bn_count + ascii_count or 1
    bn_ratio = bn_count / total
    if bn_ratio > 0.6:
        return "bn"
    if bn_ratio < 0.2:
        return "en"
    return "mixed"


# ─────────────────────────────────────────────────────────────────────────────
# Crawl-log parsing
# ─────────────────────────────────────────────────────────────────────────────

# BUG FIX: use re.MULTILINE + capture to end-of-line (.+) instead of \S+
# \S+ stops at spaces, silently dropping URLs like:
#   "alumni form.docx", "SYLLABI OF DIPLOMA CST.pdf", "Fee _Structure.pdf"
_FAILED_LINE_RE = re.compile(r"FAILED\s+\[.*?\]:\s+(.+)", re.MULTILINE)


def extract_failed_urls(log_path: Path) -> list[str]:
    """
    Read output/crawl.log and return all URLs that were marked FAILED.

    Each FAILED line looks like::

        2026-07-12 02:06:01,546 [WARNING] FAILED [?]: http://wptripura.nic.in/foo.pdf

    Note: URLs may contain literal spaces (e.g. "Fee _Structure.pdf").
    The regex captures to end-of-line to handle these correctly.
    """
    if not log_path.exists():
        return []

    urls: list[str] = []
    text = log_path.read_text(encoding="utf-8", errors="replace")
    for m in _FAILED_LINE_RE.finditer(text):
        url = m.group(1).strip()
        if url:
            urls.append(url)
    return urls


def filter_document_urls(urls: list[str]) -> list[str]:
    """
    Keep only URLs that point to supported document types.
    Deduplicates preserving order.
    """
    seen: set[str] = set()
    result: list[str] = []
    for url in urls:
        if url not in seen and is_supported(url):
            seen.add(url)
            result.append(url)
    return result


# ─────────────────────────────────────────────────────────────────────────────
# JSON serialisation
# ─────────────────────────────────────────────────────────────────────────────

def safe_json_dump(obj: Any, path: Path, indent: int = 2) -> None:
    """Write obj to path as pretty JSON (handles Path objects, etc.)."""

    class _Encoder(json.JSONEncoder):
        def default(self, o: Any) -> Any:
            if isinstance(o, Path):
                return str(o)
            return super().default(o)

    path.write_text(
        json.dumps(obj, ensure_ascii=False, indent=indent, cls=_Encoder),
        encoding="utf-8",
    )


def safe_json_load(path: Path) -> Any:
    """Load JSON from path; return None on error."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Markdown helpers
# ─────────────────────────────────────────────────────────────────────────────

def build_markdown_header(meta: dict[str, Any]) -> str:
    """
    Prepend YAML frontmatter to a Markdown document.
    """
    lines = ["---"]
    for k, v in meta.items():
        safe_v = str(v).replace('"', '\\"')
        lines.append(f'{k}: "{safe_v}"')
    lines.append("---\n")
    return "\n".join(lines)
