"""
pipeline.py — Main orchestrator for the Document Extraction Pipeline.

Execution flow per URL:
  1. Download  (downloader.py)
  2. Save raw file to output/documents/<type>/
  3. Parse     (pdf_parser / docx_parser / xlsx_parser)
  4. Build metadata
  5. Write Markdown → output/markdown/
  6. Write JSON     → output/json/
  7. Write metadata → output/metadata/
  8. Append to manifest.jsonl
  9. On any error: log to failed_documents.json, continue

Entry point: run_pipeline()
"""

from __future__ import annotations

import asyncio
import time
import traceback
from pathlib import Path
from typing import Optional

from .config import PipelineConfig, DEFAULT_CONFIG
from .downloader import AsyncDownloader
from .logger import setup_pipeline_logger, log_event, get_logger
from .manifest import ManifestWriter, FailedDocumentLog
from .metadata import build_metadata, DocumentMetadata
from .pdf_parser import parse_pdf, PdfExtractionError
from .docx_parser import parse_docx, DocxExtractionError
from .xlsx_parser import parse_xlsx, XlsxExtractionError
from .utils import (
    extract_failed_urls,
    filter_document_urls,
    get_content_type,
    url_to_filename,
    sha256_of_bytes,
    detect_language,
    count_words,
    safe_json_dump,
    build_markdown_header,
)


# ─────────────────────────────────────────────────────────────────────────────
# Per-document processor
# ─────────────────────────────────────────────────────────────────────────────

async def process_document(
    url: str,
    data: bytes,
    *,
    config: PipelineConfig,
    manifest_writer: ManifestWriter,
    failed_log: FailedDocumentLog,
) -> Optional[DocumentMetadata]:
    """
    Process one downloaded document: parse → save → manifest.

    Returns DocumentMetadata on success, None on failure.
    Never raises — all errors are caught and logged.
    """
    log = get_logger()
    content_type = get_content_type(url)
    if not content_type:
        return None

    # ── Derive stable ID and filenames ────────────────────────────────────
    base_name = url_to_filename(url)
    ext_map = {"pdf": ".pdf", "docx": ".docx", "xlsx": ".xlsx"}
    raw_ext = ext_map[content_type]

    raw_path = config.doc_dir_for_type(content_type) / f"{base_name}{raw_ext}"
    md_path  = config.markdown_dir / f"{base_name}.md"
    json_path = config.json_dir / f"{base_name}.json"

    sha256 = sha256_of_bytes(data)

    # ── Save raw file ─────────────────────────────────────────────────────
    raw_path.write_bytes(data)
    log_event(log, "SAVE", f"Raw file saved: {raw_path.name}", url=url)

    # ── Parse ─────────────────────────────────────────────────────────────
    parse_start = time.monotonic()
    try:
        if content_type == "pdf":
            result = parse_pdf(
                raw_path,
                enable_ocr=config.enable_ocr,
                do_table_structure=config.do_table_structure,
                url=url,
            )
            markdown    = result.markdown
            json_data   = result.json_data
            page_count  = result.page_count
            table_count = result.table_count
            image_count = result.image_count
            word_count  = result.word_count
            parser_used = result.parser_used

        elif content_type == "docx":
            result = parse_docx(raw_path, url=url)
            markdown    = result.markdown
            json_data   = result.json_data
            page_count  = result.page_count
            table_count = result.table_count
            image_count = result.image_count
            word_count  = result.word_count
            parser_used = result.parser_used

        else:  # xlsx
            result = parse_xlsx(raw_path, max_rows=config.xlsx_max_rows_preview, url=url)
            markdown    = result.markdown
            json_data   = result.json_data
            page_count  = 0
            table_count = result.table_count
            image_count = 0
            word_count  = result.word_count
            parser_used = result.parser_used

    except (PdfExtractionError, DocxExtractionError, XlsxExtractionError) as exc:
        failed_log.record(
            url=url,
            error=str(exc),
            stack_trace=traceback.format_exc(),
            retry_count=0,
        )
        log_event(log, "FAIL", f"Extraction failed: {exc}", level="ERROR", url=url)
        return None

    extraction_time = time.monotonic() - parse_start

    # ── Detect language ────────────────────────────────────────────────────
    language = detect_language(markdown)

    # ── Build title (first H1 or filename) ────────────────────────────────
    title = ""
    for line in markdown.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            title = stripped[2:].strip()
            break
    if not title:
        title = Path(url).stem.replace("_", " ").replace("-", " ").title()

    # ── Assemble metadata ─────────────────────────────────────────────────
    meta = build_metadata(
        doc_id=base_name,
        url=url,
        file_name=raw_path.name,
        content_type=content_type,
        sha256=sha256,
        file_size_bytes=len(data),
        source=config.source_domain,
        title=title,
        language=language,
        page_count=page_count,
        tables=table_count,
        images=image_count,
        word_count=word_count,
        parser_used=parser_used,
        extraction_time_s=round(extraction_time, 3),
        processing_status="success",
        local_path=str(raw_path),
        markdown_path=str(md_path),
        json_path=str(json_path),
    )

    # ── Write Markdown (with frontmatter) ─────────────────────────────────
    frontmatter = build_markdown_header({
        "id":           meta.id,
        "url":          meta.url,
        "title":        meta.title,
        "content_type": meta.content_type,
        "source":       meta.source,
        "language":     meta.language,
        "page_count":   meta.page_count,
        "tables":       meta.tables,
        "word_count":   meta.word_count,
        "parser":       meta.parser_used,
        "download_date": meta.download_date,
    })
    md_path.write_text(frontmatter + "\n" + markdown, encoding="utf-8")
    log_event(log, "SAVE", f"Markdown saved: {md_path.name}", url=url)

    # ── Write JSON ────────────────────────────────────────────────────────
    json_envelope: dict = {
        "metadata": meta.to_dict(),
        "content":  json_data,
    }
    safe_json_dump(json_envelope, json_path)
    log_event(log, "SAVE", f"JSON saved: {json_path.name}", url=url)

    # ── Write metadata file ───────────────────────────────────────────────
    meta.save(config.metadata_dir)
    log_event(log, "SAVE", f"Metadata saved: {meta.id}.metadata.json", url=url)

    # ── Append to manifest ────────────────────────────────────────────────
    manifest_writer.append(meta)

    log_event(
        log, "COMPLETE",
        f"✓ {content_type.upper()} | {word_count:,} words | {parser_used} | {url}",
    )
    return meta


# ─────────────────────────────────────────────────────────────────────────────
# Pipeline orchestrator
# ─────────────────────────────────────────────────────────────────────────────

async def run_pipeline(
    config: PipelineConfig = DEFAULT_CONFIG,
    extra_urls: list[str] | None = None,
) -> dict:
    """
    Run the full document extraction pipeline.

    Parameters
    ----------
    config:
        Pipeline configuration (paths, limits, options).
    extra_urls:
        If provided, use these URLs instead of reading from crawl.log.
        Useful for targeted re-processing.

    Returns
    -------
    dict with summary statistics.
    """
    # ── Setup ─────────────────────────────────────────────────────────────
    config.create_all_dirs()
    log = setup_pipeline_logger(config.logs_dir)

    log_event(log, "START", "=" * 60)
    log_event(log, "START", "Document Extraction Pipeline — West Tripura RAG")
    log_event(log, "START", f"Output root  : {config.output_root.resolve()}")
    log_event(log, "START", f"Concurrency  : {config.download_concurrency}")
    log_event(log, "START", f"OCR enabled  : {config.enable_ocr}")
    log_event(log, "START", "=" * 60)

    manifest_writer = ManifestWriter(config.manifest_path)
    failed_log      = FailedDocumentLog(config.failed_docs_path)

    # ── Collect URLs ───────────────────────────────────────────────────────
    if extra_urls is not None:
        all_failed = extra_urls
    else:
        all_failed = extract_failed_urls(config.crawl_log_path)

    doc_urls = filter_document_urls(all_failed)
    log_event(log, "START", f"Total failed URLs : {len(all_failed)}")
    log_event(log, "START", f"Document URLs     : {len(doc_urls)}")

    if not doc_urls:
        log_event(log, "COMPLETE", "No document URLs found — pipeline finished.")
        return {"processed": 0, "failed": 0, "skipped": 0}

    # ── Skip already-processed URLs ────────────────────────────────────────
    already_done = manifest_writer.load_existing_urls()
    pending = [u for u in doc_urls if u not in already_done]
    skipped = len(doc_urls) - len(pending)

    if skipped:
        log_event(log, "START", f"Skipping {skipped} already-processed URLs (resume mode)")

    log_event(log, "START", f"URLs to process   : {len(pending)}")

    # ── Download + Process ─────────────────────────────────────────────────
    pipeline_start = time.monotonic()
    processed = 0
    failed    = 0

    async with AsyncDownloader(config) as downloader:
        # Process in batches to avoid holding all bytes in memory
        batch_size = config.download_concurrency * 4
        for batch_start in range(0, len(pending), batch_size):
            batch = pending[batch_start : batch_start + batch_size]

            log_event(
                log, "DOWNLOAD",
                f"Batch {batch_start // batch_size + 1}: "
                f"downloading {len(batch)} URLs …",
            )

            download_results = await downloader.download_many(batch)

            for dl in download_results:
                if not dl.success:
                    failed += 1
                    failed_log.record(
                        url=dl.url,
                        error=dl.error,
                        retry_count=dl.retry_count,
                    )
                    continue

                meta = await process_document(
                    dl.url,
                    dl.data,
                    config=config,
                    manifest_writer=manifest_writer,
                    failed_log=failed_log,
                )

                if meta is not None:
                    processed += 1
                else:
                    failed += 1

    # ── Summary ────────────────────────────────────────────────────────────
    elapsed = time.monotonic() - pipeline_start
    summary = {
        "processed": processed,
        "failed":    failed,
        "skipped":   skipped,
        "total_urls": len(doc_urls),
        "elapsed_s": round(elapsed, 1),
    }

    log_event(log, "COMPLETE", "=" * 60)
    log_event(log, "COMPLETE", f"Pipeline finished in {elapsed:.1f}s")
    log_event(log, "COMPLETE", f"  Processed : {processed}")
    log_event(log, "COMPLETE", f"  Failed    : {failed}")
    log_event(log, "COMPLETE", f"  Skipped   : {skipped} (already done)")
    log_event(log, "COMPLETE", f"  Manifest  : {config.manifest_path}")
    log_event(log, "COMPLETE", f"  Failures  : {config.failed_docs_path}")
    log_event(log, "COMPLETE", "=" * 60)

    return summary
