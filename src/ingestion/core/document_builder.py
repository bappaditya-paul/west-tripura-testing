"""
ingestion/document_builder.py
=============================
MODULE 1 — Unified Document Builder

Reads every source from:
  - output/pages/    (HTML → Markdown, from Crawl4AI)
  - output/json/     (PDF/DOCX/XLSX → Docling JSON)
  - output/metadata/ (per-document metadata JSON)
  - output/manifest.jsonl (URL → file mapping)

Produces one canonical JSON document per source:
  processed_documents/<document_id>.json

Also writes:
  processed_documents/index.json

Canonical document schema
─────────────────────────
{
    "document_id": str,
    "source_type": "html" | "pdf" | "docx" | "xlsx",
    "title": str,
    "url": str,
    "content": str,          # clean full text (Markdown)
    "headings": [...],
    "tables": [...],
    "metadata": { ... }
}
"""

from __future__ import annotations

import json
import time
import traceback
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .config import IngestionConfig, DEFAULT_CONFIG
from .metadata import build_html_metadata, build_doc_metadata, DocumentMetadata
from .parser import (
    parse_markdown, extract_headings, extract_tables,
    extract_title, blocks_to_text,
)
from .utils import (
    setup_logger, log_event, FailedRegistry,
    make_document_id, content_hash, clean_text,
    parse_frontmatter, safe_json_load, safe_json_dump, count_words,
)


# ─────────────────────────────────────────────────────────────────────────────
# Canonical document dataclass
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class CanonicalDocument:
    document_id: str
    source_type: str                        # html | pdf | docx | xlsx
    title: str
    url: str
    content: str                            # clean Markdown text
    headings: list[dict[str, Any]] = field(default_factory=list)
    tables: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def save(self, out_dir: Path) -> Path:
        path = out_dir / f"{self.document_id}.json"
        safe_json_dump(self.to_dict(), path)
        return path


# ─────────────────────────────────────────────────────────────────────────────
# Manifest loader
# ─────────────────────────────────────────────────────────────────────────────

def _load_manifest(manifest_path: Path) -> dict[str, dict[str, Any]]:
    """
    Load manifest.jsonl → dict keyed by URL.
    Handles both crawler manifest (no parser_used) and
    document_pipeline manifest (with parser_used).
    """
    url_map: dict[str, dict[str, Any]] = {}
    if not manifest_path.exists():
        return url_map
    for line in manifest_path.read_text(encoding="utf-8").splitlines():
        try:
            rec = json.loads(line)
            if url := rec.get("url"):
                url_map[url] = rec
        except Exception:
            pass
    return url_map


# ─────────────────────────────────────────────────────────────────────────────
# HTML page builder
# ─────────────────────────────────────────────────────────────────────────────

def _build_from_html(
    md_path: Path,
    manifest: dict[str, dict[str, Any]],
) -> CanonicalDocument:
    """
    Build a CanonicalDocument from a Crawl4AI Markdown page.
    """
    raw = md_path.read_text(encoding="utf-8")
    frontmatter, body = parse_frontmatter(raw)

    url = frontmatter.get("url", "")
    manifest_entry = manifest.get(url) if url else None

    # Clean & parse
    body = clean_text(body)
    blocks = parse_markdown(body)

    title = extract_title(blocks) or frontmatter.get("title", "")
    if not title:
        title = md_path.stem.replace("__", " ").replace("_", " ").title()

    headings = extract_headings(blocks)
    tables   = extract_tables(blocks)
    content  = blocks_to_text(blocks)

    doc_id = make_document_id(url or md_path.name, md_path.stem)
    meta   = build_html_metadata(
        frontmatter=frontmatter,
        manifest_entry=manifest_entry,
        content=content,
    )

    return CanonicalDocument(
        document_id=doc_id,
        source_type="html",
        title=title,
        url=url,
        content=content,
        headings=headings,
        tables=tables,
        metadata=meta.to_dict(),
    )


# ─────────────────────────────────────────────────────────────────────────────
# PDF / DOCX / XLSX builder
# ─────────────────────────────────────────────────────────────────────────────

def _build_from_doc_json(
    json_path: Path,
    metadata_dir: Path,
) -> CanonicalDocument:
    """
    Build a CanonicalDocument from Docling/openpyxl JSON + metadata file.

    JSON envelope (from document_pipeline):
    {
        "metadata": { ... },
        "content": { ... Docling dict or openpyxl dict ... }
    }
    """
    envelope = safe_json_load(json_path)
    if envelope is None:
        raise ValueError(f"Cannot parse JSON: {json_path}")

    raw_meta: dict[str, Any] = envelope.get("metadata", {})
    content_obj: dict[str, Any] = envelope.get("content", {})

    # Try to find a parallel .metadata.json file
    meta_path = metadata_dir / f"{json_path.stem}.metadata.json"
    if meta_path.exists():
        file_meta = safe_json_load(meta_path) or {}
        raw_meta = {**file_meta, **raw_meta}  # envelope metadata takes priority

    url          = raw_meta.get("url", "")
    source_type  = raw_meta.get("content_type", "pdf")

    # ── Extract markdown from content object ───────────────────────────
    # Docling JSON may have 'raw_markdown' or a body dict
    markdown_text = ""
    if isinstance(content_obj, dict):
        markdown_text = content_obj.get("raw_markdown", "")
        if not markdown_text:
            # Try to reconstruct from Docling body items
            markdown_text = _reconstruct_docling_markdown(content_obj)
    elif isinstance(content_obj, str):
        markdown_text = content_obj

    markdown_text = clean_text(markdown_text)

    # ── Also try reading the .md file for a clean version ─────────────
    # document_pipeline writes output/markdown/<stem>.md
    blocks = parse_markdown(markdown_text) if markdown_text else []

    title    = extract_title(blocks) or raw_meta.get("title", "")
    if not title:
        title = Path(raw_meta.get("file_name", json_path.stem)).stem \
                    .replace("_", " ").replace("-", " ").title()

    headings = extract_headings(blocks)
    tables   = extract_tables(blocks) or _extract_xlsx_tables(content_obj)
    content  = blocks_to_text(blocks) if blocks else markdown_text

    doc_id = make_document_id(url or json_path.name, json_path.stem)
    meta   = build_doc_metadata(raw_meta=raw_meta, content=content)

    # Patch table count from parsed tables if metadata shows 0
    if meta.table_count == 0:
        meta.table_count = len(tables)

    return CanonicalDocument(
        document_id=doc_id,
        source_type=source_type,
        title=title,
        url=url,
        content=content,
        headings=headings,
        tables=tables,
        metadata=meta.to_dict(),
    )


def _reconstruct_docling_markdown(content_obj: dict[str, Any]) -> str:
    """
    Best-effort text extraction from a Docling export_to_dict() object.
    Docling structure varies by version; we try common patterns.
    """
    # Pattern 1: direct 'text' field
    if text := content_obj.get("text"):
        return str(text)

    # Pattern 2: body items list
    parts: list[str] = []
    body = content_obj.get("body", [])
    if isinstance(body, list):
        for item in body:
            if isinstance(item, dict):
                t = item.get("text") or item.get("content") or ""
                if t:
                    label = item.get("label", "")
                    if "heading" in label.lower():
                        level = item.get("level", 2)
                        parts.append(f"{'#' * level} {t}")
                    else:
                        parts.append(t)
            elif isinstance(item, str):
                parts.append(item)
    elif isinstance(body, dict):
        # body might be a dictionary containing children/texts
        pass

    # Pattern 3: pages list
    pages = content_obj.get("pages", [])
    if isinstance(pages, dict):
        pages = list(pages.values())
    if isinstance(pages, list):
        for page in pages:
            if isinstance(page, dict):
                cells = page.get("cells", [])
                if isinstance(cells, list):
                    for cell in cells:
                        if isinstance(cell, dict):
                            if t := cell.get("text"):
                                parts.append(t)

    # Pattern 4: top-level texts array (newer Docling)
    texts = content_obj.get("texts", [])
    if isinstance(texts, list):
        for item in texts:
            if isinstance(item, dict):
                if t := item.get("text"):
                    parts.append(t)

    return "\n\n".join(p for p in parts if p.strip())


def _extract_xlsx_tables(content_obj: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Extract tables from an openpyxl JSON structure (sheets list).
    """
    tables = []
    for sheet in content_obj.get("sheets", []):
        if isinstance(sheet, dict):
            tables.append({
                "sheet_name": sheet.get("sheet_name", ""),
                "headers":    sheet.get("headers", []),
                "rows":       sheet.get("rows", []),
                "row_count":  sheet.get("row_count", 0),
                "col_count":  sheet.get("col_count", 0),
                "raw":        "",
            })
    return tables


# ─────────────────────────────────────────────────────────────────────────────
# Also support reading from output/markdown/*.md (doc pipeline output)
# ─────────────────────────────────────────────────────────────────────────────

def _build_from_doc_markdown(
    md_path: Path,
    metadata_dir: Path,
    manifest: dict[str, dict[str, Any]],
) -> CanonicalDocument:
    """
    Build CanonicalDocument from a document_pipeline Markdown file.
    These files live in output/markdown/ and have richer frontmatter.
    """
    raw = md_path.read_text(encoding="utf-8")
    frontmatter, body = parse_frontmatter(raw)

    url         = frontmatter.get("url", "")
    source_type = frontmatter.get("content_type", "pdf")

    # Try to load the parallel metadata file
    meta_path = metadata_dir / f"{md_path.stem}.metadata.json"
    raw_meta: dict[str, Any] = {}
    if meta_path.exists():
        raw_meta = safe_json_load(meta_path) or {}

    body = clean_text(body)
    blocks = parse_markdown(body)

    title    = extract_title(blocks) or frontmatter.get("title", "")
    headings = extract_headings(blocks)
    tables   = extract_tables(blocks)
    content  = blocks_to_text(blocks)

    doc_id = make_document_id(url or md_path.name, md_path.stem)

    # Merge frontmatter into raw_meta for metadata builder
    merged_meta = {
        "url":          url,
        "content_type": source_type,
        "title":        title,
        "parser_used":  frontmatter.get("parser", raw_meta.get("parser_used", "")),
        "language":     frontmatter.get("language", raw_meta.get("language", "")),
        "page_count":   int(frontmatter.get("page_count", raw_meta.get("page_count", 0))),
        "tables":       int(frontmatter.get("tables", raw_meta.get("tables", 0))),
        "word_count":   int(frontmatter.get("word_count", raw_meta.get("word_count", 0))),
        "download_date": frontmatter.get("download_date", raw_meta.get("download_date", "")),
        **raw_meta,
    }
    meta = build_doc_metadata(raw_meta=merged_meta, content=content)

    return CanonicalDocument(
        document_id=doc_id,
        source_type=source_type,
        title=title,
        url=url,
        content=content,
        headings=headings,
        tables=tables,
        metadata=meta.to_dict(),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Main builder
# ─────────────────────────────────────────────────────────────────────────────

def build_documents(config: IngestionConfig = DEFAULT_CONFIG) -> dict[str, Any]:
    """
    Process all sources and write canonical JSON documents.

    Returns a summary dict.
    """
    config.create_all_dirs()
    log = setup_logger("document_builder", config.logs_dir / "document_builder.log")
    failed = FailedRegistry(config.failed_documents_path)

    log_event(log, "START", "=" * 60)
    log_event(log, "START", "Document Builder — West Tripura RAG")
    log_event(log, "START", f"Output: {config.processed_docs_dir.resolve()}")

    manifest = _load_manifest(config.manifest_path)
    log_event(log, "START", f"Manifest entries: {len(manifest)}")

    index: list[dict[str, Any]] = []
    processed = 0
    skipped   = 0
    errors    = 0

    # ── Track processed document_ids to avoid duplicates ──────────────────
    seen_ids: set[str] = set()

    # ─────────────────────────────────────────────────────────────────────
    # Source 1: HTML pages (output/pages/*.md)
    # ─────────────────────────────────────────────────────────────────────
    html_files = sorted(config.pages_dir.glob("*.md")) if config.pages_dir.exists() else []
    log_event(log, "PROCESS", f"HTML pages found: {len(html_files)}")

    for md_path in html_files:
        t0 = time.monotonic()
        try:
            doc = _build_from_html(md_path, manifest)

            if doc.document_id in seen_ids:
                skipped += 1
                continue
            seen_ids.add(doc.document_id)

            # Skip near-empty documents
            if count_words(doc.content) < 10:
                log_event(log, "WARNING", f"Skipping near-empty page: {md_path.name}",
                          level="WARNING")
                skipped += 1
                continue

            out_path = doc.save(config.processed_docs_dir)
            elapsed = time.monotonic() - t0

            index.append({
                "document_id": doc.document_id,
                "title":       doc.title,
                "url":         doc.url,
                "source_type": doc.source_type,
                "file":        out_path.name,
            })
            processed += 1
            log_event(log, "SAVE",
                      f"[html] {doc.document_id} | {count_words(doc.content):,}w | {elapsed:.2f}s",
                      doc_id=doc.document_id)

        except Exception as exc:
            errors += 1
            failed.record(file=str(md_path), error=str(exc), stage="html_build")
            log_event(log, "ERROR", f"Failed {md_path.name}: {exc}",
                      level="ERROR", file=str(md_path))

    # ─────────────────────────────────────────────────────────────────────
    # Source 2: Document pipeline Markdown (output/markdown/*.md)
    # ─────────────────────────────────────────────────────────────────────
    doc_md_dir = config.pages_dir.parent / "markdown"
    doc_md_files = sorted(doc_md_dir.glob("*.md")) if doc_md_dir.exists() else []
    log_event(log, "PROCESS", f"Document Markdown files: {len(doc_md_files)}")

    for md_path in doc_md_files:
        t0 = time.monotonic()
        try:
            doc = _build_from_doc_markdown(md_path, config.metadata_dir, manifest)

            if doc.document_id in seen_ids:
                skipped += 1
                continue
            seen_ids.add(doc.document_id)

            if count_words(doc.content) < 5:
                skipped += 1
                continue

            out_path = doc.save(config.processed_docs_dir)
            elapsed = time.monotonic() - t0

            index.append({
                "document_id": doc.document_id,
                "title":       doc.title,
                "url":         doc.url,
                "source_type": doc.source_type,
                "file":        out_path.name,
            })
            processed += 1
            log_event(log, "SAVE",
                      f"[{doc.source_type}] {doc.document_id} | {count_words(doc.content):,}w | {elapsed:.2f}s",
                      doc_id=doc.document_id)

        except Exception as exc:
            errors += 1
            failed.record(file=str(md_path), error=str(exc), stage="doc_md_build")
            log_event(log, "ERROR", f"Failed {md_path.name}: {exc}",
                      level="ERROR", file=str(md_path))

    # ─────────────────────────────────────────────────────────────────────
    # Source 3: Docling JSON (output/json/*.json) — only if no .md yet
    # ─────────────────────────────────────────────────────────────────────
    json_files = sorted(config.json_dir.glob("*.json")) if config.json_dir.exists() else []
    log_event(log, "PROCESS", f"Docling JSON files: {len(json_files)}")

    for json_path in json_files:
        t0 = time.monotonic()
        try:
            doc = _build_from_doc_json(json_path, config.metadata_dir)

            if doc.document_id in seen_ids:
                skipped += 1
                continue
            seen_ids.add(doc.document_id)

            if count_words(doc.content) < 5:
                skipped += 1
                continue

            out_path = doc.save(config.processed_docs_dir)
            elapsed = time.monotonic() - t0

            index.append({
                "document_id": doc.document_id,
                "title":       doc.title,
                "url":         doc.url,
                "source_type": doc.source_type,
                "file":        out_path.name,
            })
            processed += 1
            log_event(log, "SAVE",
                      f"[json] {doc.document_id} | {elapsed:.2f}s",
                      doc_id=doc.document_id)

        except Exception as exc:
            errors += 1
            failed.record(file=str(json_path), error=str(exc), stage="json_build")
            log_event(log, "ERROR", f"Failed {json_path.name}: {exc}",
                      level="ERROR", file=str(json_path))

    # ── Write index ────────────────────────────────────────────────────────
    index_path = config.processed_docs_dir / "index.json"
    safe_json_dump({"total": len(index), "documents": index}, index_path)

    summary = {
        "processed": processed,
        "skipped":   skipped,
        "errors":    errors,
        "total":     processed + skipped + errors,
        "index":     str(index_path),
    }

    log_event(log, "COMPLETE", "=" * 60)
    log_event(log, "COMPLETE", f"Documents built : {processed}")
    log_event(log, "COMPLETE", f"Skipped         : {skipped}")
    log_event(log, "COMPLETE", f"Errors          : {errors}")
    log_event(log, "COMPLETE", f"Index           : {index_path}")
    log_event(log, "COMPLETE", "=" * 60)

    return summary
