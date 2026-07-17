"""
docx_parser.py — DOCX / DOC extraction using Docling.

Preserves:
  - Headings (H1 … H6)
  - Paragraphs
  - Tables (with structure)
  - Lists (ordered / unordered)

Outputs:
  - Markdown string
  - Structured JSON dict
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .logger import get_logger, log_event

log = get_logger()


# ─────────────────────────────────────────────────────────────────────────────
# Result dataclass
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class DocxParseResult:
    markdown: str = ""
    json_data: dict[str, Any] = None    # type: ignore[assignment]
    page_count: int = 0
    table_count: int = 0
    image_count: int = 0
    word_count: int = 0
    parser_used: str = "docling"
    duration_s: float = 0.0
    success: bool = False
    error: str = ""

    def __post_init__(self):
        if self.json_data is None:
            self.json_data = {}


class DocxExtractionError(Exception):
    """Raised when DOCX extraction fails."""


# ─────────────────────────────────────────────────────────────────────────────
# Docling converter factory for DOCX
# ─────────────────────────────────────────────────────────────────────────────

def _make_docx_converter():
    try:
        from docling.document_converter import DocumentConverter, WordFormatOption
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import WordPipelineOptions

        opts = WordPipelineOptions()

        return DocumentConverter(
            format_options={
                InputFormat.DOCX: WordFormatOption(pipeline_options=opts)
            }
        )
    except ImportError as exc:
        raise ImportError("Docling is not installed. Run: pip install docling") from exc
    except Exception:
        # Older Docling versions may not have WordFormatOption — fall back to plain
        try:
            from docling.document_converter import DocumentConverter
            return DocumentConverter()
        except ImportError as exc2:
            raise ImportError("Docling is not installed.") from exc2


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def parse_docx(
    docx_path: Path,
    *,
    url: str = "",
) -> DocxParseResult:
    """
    Extract content from a DOCX (or DOC) file using Docling.

    Parameters
    ----------
    docx_path:
        Path to the downloaded DOCX/DOC file.
    url:
        Original URL (used only for logging).
    """
    t0 = time.monotonic()
    log_event(log, "PARSE", f"Parsing DOCX: {docx_path.name}", url=url)

    try:
        converter = _make_docx_converter()
        conv_result = converter.convert(str(docx_path))
        doc = conv_result.document

        markdown: str = doc.export_to_markdown()

        # ── JSON export ────────────────────────────────────────────────
        try:
            json_data: dict[str, Any] = doc.export_to_dict()
        except Exception:
            json_data = {"raw_markdown": markdown}

        # ── Statistics ─────────────────────────────────────────────────
        table_count = 0
        image_count = 0
        page_count = 0

        try:
            page_count = doc.num_pages()
        except Exception:
            pass

        try:
            from docling.datamodel.base_models import ItemLabel
            for item, _ in doc.iterate_items():
                label = getattr(item, "label", None)
                if label == ItemLabel.TABLE:
                    table_count += 1
                elif label in (ItemLabel.PICTURE, ItemLabel.FIGURE):
                    image_count += 1
        except Exception:
            table_count = markdown.count("\n|")

        if not markdown.strip():
            raise DocxExtractionError(f"Docling produced empty output for {docx_path.name}")

        elapsed = time.monotonic() - t0
        word_count = len(markdown.split())

        log_event(
            log, "PARSE",
            f"DOCX parsed: {table_count} tables · {word_count:,} words in {elapsed:.1f}s",
            url=url, duration_s=round(elapsed, 3),
        )

        return DocxParseResult(
            markdown=markdown,
            json_data=json_data,
            page_count=page_count,
            table_count=table_count,
            image_count=image_count,
            word_count=word_count,
            parser_used="docling",
            duration_s=round(elapsed, 3),
            success=True,
        )

    except DocxExtractionError:
        raise
    except Exception as exc:
        elapsed = time.monotonic() - t0
        msg = f"{type(exc).__name__}: {exc}"
        log_event(log, "FAIL", f"DOCX parse error: {msg}", level="ERROR", url=url)
        raise DocxExtractionError(msg) from exc
