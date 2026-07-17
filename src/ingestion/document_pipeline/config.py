"""
config.py — Central configuration for the Document Extraction Pipeline.

All paths, limits, and toggles live here.
Change values here; nothing else needs editing for most deployments.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


# ─────────────────────────────────────────────────────────────────────────────
# File-type routing
# ─────────────────────────────────────────────────────────────────────────────

#: Extensions routed to the PDF parser (Docling)
PDF_EXTENSIONS: frozenset[str] = frozenset({".pdf"})

#: Extensions routed to the DOCX parser (Docling)
DOCX_EXTENSIONS: frozenset[str] = frozenset({".docx", ".doc"})

#: Extensions routed to the XLSX parser (openpyxl)
XLSX_EXTENSIONS: frozenset[str] = frozenset({".xlsx", ".xls"})

#: All supported extensions (union of above)
SUPPORTED_EXTENSIONS: frozenset[str] = (
    PDF_EXTENSIONS | DOCX_EXTENSIONS | XLSX_EXTENSIONS
)

#: Extensions to silently skip (images, video, archives, web assets)
IGNORED_EXTENSIONS: frozenset[str] = frozenset({
    ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".svg", ".ico",
    ".mp4", ".avi", ".mov", ".mkv", ".wmv",
    ".zip", ".tar", ".gz", ".rar", ".7z",
    ".css", ".js", ".json", ".xml", ".html", ".htm",
    ".txt", ".csv",
})

#: Website source label embedded in every metadata record
SOURCE_DOMAIN: str = "westtripura.nic.in"


# ─────────────────────────────────────────────────────────────────────────────
# Pipeline configuration dataclass
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class PipelineConfig:
    """All runtime parameters for the extraction pipeline."""

    # ── Root directories ─────────────────────────────────────────────────────
    workspace_root: Path = field(default_factory=lambda: Path("."))
    output_root: Path = field(default_factory=lambda: Path("output"))

    # ── Derived output directories (set in __post_init__) ────────────────────
    docs_pdf_dir: Path = field(init=False)
    docs_docx_dir: Path = field(init=False)
    docs_xlsx_dir: Path = field(init=False)
    markdown_dir: Path = field(init=False)
    json_dir: Path = field(init=False)
    metadata_dir: Path = field(init=False)
    logs_dir: Path = field(init=False)

    # ── Input sources ────────────────────────────────────────────────────────
    crawl_log_path: Path = field(init=False)       # output/crawl.log
    manifest_path: Path = field(init=False)        # output/manifest.jsonl
    failed_docs_path: Path = field(init=False)     # output/failed_documents.json

    # ── Network ──────────────────────────────────────────────────────────────
    download_concurrency: int = 3           # parallel downloads (polite for govt)
    request_timeout: int = 60              # seconds per request
    max_retries: int = 3                   # per URL
    retry_base_delay: float = 2.0          # seconds; doubles each retry (exp backoff)
    chunk_size: int = 1024 * 64            # 64 KB streaming chunks

    # ── HTTP headers ─────────────────────────────────────────────────────────
    user_agent: str = (
        "Mozilla/5.0 (compatible; WestTripuraRAGBot/1.0; "
        "+https://westtripura.nic.in)"
    )

    # ── Docling PDF options ───────────────────────────────────────────────────
    enable_ocr: bool = True                # OCR fallback when text extraction fails
    do_table_structure: bool = True        # Extract tables from PDFs

    # ── XLSX options ─────────────────────────────────────────────────────────
    xlsx_max_rows_preview: int = 1000      # safety cap for huge sheets

    # ── Source label ─────────────────────────────────────────────────────────
    source_domain: str = SOURCE_DOMAIN

    def __post_init__(self) -> None:
        out = self.output_root
        self.docs_pdf_dir  = out / "documents" / "pdf"
        self.docs_docx_dir = out / "documents" / "docx"
        self.docs_xlsx_dir = out / "documents" / "xlsx"
        self.markdown_dir  = out / "markdown"
        self.json_dir      = out / "json"
        self.metadata_dir  = out / "metadata"
        self.logs_dir      = out / "logs"

        self.crawl_log_path    = out / "crawl.log"
        self.manifest_path     = out / "manifest.jsonl"
        self.failed_docs_path  = out / "failed_documents.json"

    def create_all_dirs(self) -> None:
        """Create the full output directory tree."""
        for d in [
            self.docs_pdf_dir,
            self.docs_docx_dir,
            self.docs_xlsx_dir,
            self.markdown_dir,
            self.json_dir,
            self.metadata_dir,
            self.logs_dir,
        ]:
            d.mkdir(parents=True, exist_ok=True)

    def doc_dir_for_type(self, content_type: str) -> Path:
        """Return the raw-document storage directory for a given type."""
        mapping = {
            "pdf": self.docs_pdf_dir,
            "docx": self.docs_docx_dir,
            "xlsx": self.docs_xlsx_dir,
        }
        return mapping.get(content_type, self.docs_pdf_dir)


# ─────────────────────────────────────────────────────────────────────────────
# Singleton default config (override in pipeline.py if needed)
# ─────────────────────────────────────────────────────────────────────────────
DEFAULT_CONFIG = PipelineConfig()
