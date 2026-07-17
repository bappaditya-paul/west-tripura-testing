"""
pdf_parser.py — PDF extraction using Docling (primary) with OCR fallback.

Strategy:
  1. Try Docling standard pipeline (text-based PDF)
  2. If extracted text is suspiciously short → retry with Docling OCR pipeline
  3. If OCR also fails → raise PdfExtractionError with full context

Outputs per document:
  - Markdown string (with YAML frontmatter)
  - Structured JSON dict (Docling export + our metadata envelope)
"""

from __future__ import annotations

import time
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .logger import get_logger, log_event

log = get_logger()

# ─────────────────────────────────────────────────────────────────────────────
# Docling imports (lazy — only imported when needed so the rest of the
# pipeline still works if Docling is not yet installed)
# ─────────────────────────────────────────────────────────────────────────────

def _import_docling():
    """Import Docling components; raise ImportError with install hint if missing."""
    try:
        from docling.document_converter import DocumentConverter, PdfFormatOption
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import PdfPipelineOptions
        return DocumentConverter, PdfFormatOption, InputFormat, PdfPipelineOptions
    except ImportError as exc:
        raise ImportError(
            "Docling is not installed. Run: pip install docling"
        ) from exc


# ─────────────────────────────────────────────────────────────────────────────
# Result dataclass
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class PdfParseResult:
    markdown: str = ""
    json_data: dict[str, Any] = None        # type: ignore[assignment]
    page_count: int = 0
    table_count: int = 0
    image_count: int = 0
    word_count: int = 0
    parser_used: str = ""                   # "docling" or "docling+ocr"
    duration_s: float = 0.0
    success: bool = False
    error: str = ""

    def __post_init__(self):
        if self.json_data is None:
            self.json_data = {}


class PdfExtractionError(Exception):
    """Raised when all PDF extraction strategies fail."""


# ─────────────────────────────────────────────────────────────────────────────
# OCR-threshold heuristic
# ─────────────────────────────────────────────────────────────────────────────

_MIN_WORDS_PER_PAGE = 10   # fewer than this per page → likely scanned → need OCR


def _needs_ocr(markdown: str, page_count: int) -> bool:
    """Return True if the extracted text is too sparse for a text-based PDF."""
    if not markdown.strip():
        return True
    word_count = len(markdown.split())
    pages = max(page_count, 1)
    return (word_count / pages) < _MIN_WORDS_PER_PAGE


# ─────────────────────────────────────────────────────────────────────────────
# Docling converter factory
# ─────────────────────────────────────────────────────────────────────────────

def _make_converter(enable_ocr: bool, do_table_structure: bool):
    """Build a DocumentConverter with appropriate pipeline options."""
    DocumentConverter, PdfFormatOption, InputFormat, PdfPipelineOptions = _import_docling()

    opts = PdfPipelineOptions()
    opts.do_ocr = enable_ocr
    opts.do_table_structure = do_table_structure

    return DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(pipeline_options=opts)
        }
    )


# ─────────────────────────────────────────────────────────────────────────────
# Parse a saved PDF file
# ─────────────────────────────────────────────────────────────────────────────

def parse_pdf(
    pdf_path: Path,
    *,
    enable_ocr: bool = True,
    do_table_structure: bool = True,
    url: str = "",
) -> PdfParseResult:
    """
    Extract content from a PDF file using Docling.

    Parameters
    ----------
    pdf_path:
        Path to the already-downloaded PDF file.
    enable_ocr:
        If True, fall back to OCR when text extraction yields sparse output.
    do_table_structure:
        If True, Docling will attempt to reconstruct table structure.
    url:
        Original URL (used only for logging).

    Returns
    -------
    PdfParseResult
        Contains markdown, json_data, stats, parser name.

    Raises
    ------
    PdfExtractionError
        When ALL strategies fail.
    """
    t0 = time.monotonic()
    log_event(log, "PARSE", f"Parsing PDF: {pdf_path.name}", url=url)

    # ── Phase 1: standard (text-based) extraction ─────────────────────────
    result = _run_docling(
        pdf_path,
        enable_ocr=False,
        do_table_structure=do_table_structure,
        url=url,
    )

    if result is None:
        raise PdfExtractionError(f"Docling failed to load: {pdf_path}")

    markdown, json_data, page_count, table_count, image_count = result
    parser_used = "docling"

    # ── Phase 2: OCR fallback if text is too sparse ───────────────────────
    if enable_ocr and _needs_ocr(markdown, page_count):
        log_event(
            log, "PARSE",
            f"Text too sparse ({len(markdown.split())} words / {page_count} pages) "
            "→ switching to OCR",
            url=url, level="WARNING",
        )
        ocr_result = _run_docling(
            pdf_path,
            enable_ocr=True,
            do_table_structure=do_table_structure,
            url=url,
        )
        if ocr_result is not None:
            markdown, json_data, page_count, table_count, image_count = ocr_result
            parser_used = "docling+ocr"
        else:
            log_event(log, "FAIL", "OCR pass also failed — keeping sparse output",
                      url=url, level="WARNING")

    # ── Still empty? ─────────────────────────────────────────────────────
    if not markdown.strip():
        raise PdfExtractionError(
            f"All extraction strategies yielded empty output for {pdf_path.name}"
        )

    elapsed = time.monotonic() - t0
    word_count = len(markdown.split())

    log_event(
        log, "PARSE",
        f"PDF parsed [{parser_used}]: {page_count}pp · "
        f"{table_count} tables · {word_count:,} words in {elapsed:.1f}s",
        url=url, duration_s=round(elapsed, 3),
    )

    return PdfParseResult(
        markdown=markdown,
        json_data=json_data,
        page_count=page_count,
        table_count=table_count,
        image_count=image_count,
        word_count=word_count,
        parser_used=parser_used,
        duration_s=round(elapsed, 3),
        success=True,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Internal Docling runner
# ─────────────────────────────────────────────────────────────────────────────

def _run_docling(
    pdf_path: Path,
    *,
    enable_ocr: bool,
    do_table_structure: bool,
    url: str = "",
) -> tuple[str, dict[str, Any], int, int, int] | None:
    """
    Run Docling on pdf_path.

    Returns (markdown, json_dict, page_count, table_count, image_count)
    or None on hard failure.
    """
    try:
        converter = _make_converter(enable_ocr=enable_ocr, do_table_structure=do_table_structure)
        conv_result = converter.convert(str(pdf_path))
        doc = conv_result.document

        markdown: str = doc.export_to_markdown()

        # ── JSON export ────────────────────────────────────────────────
        try:
            json_data: dict[str, Any] = doc.export_to_dict()
        except Exception:
            json_data = {"raw_markdown": markdown}

        # ── Statistics ─────────────────────────────────────────────────
        page_count: int = 0
        table_count: int = 0
        image_count: int = 0

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
            # Fallback: count markdown table markers
            table_count = markdown.count("\n|")

        return markdown, json_data, page_count, table_count, image_count

    except Exception as exc:
        log_event(
            log, "FAIL",
            f"Docling error (ocr={enable_ocr}): {exc}",
            level="WARNING", url=url,
        )
        return None
