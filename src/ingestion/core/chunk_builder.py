"""
ingestion/chunk_builder.py
==========================
MODULE 2 — Semantic Chunk Builder

Input:  processed_documents/*.json   (from Module 1)
Output: processed_chunks/chunk_NNNNNN.json

Chunking philosophy
-------------------
Chunks are built from the document's *structural blocks*, NOT by character
or token count. The hierarchy respected is:

    Heading
      └── Paragraph / List
      └── Table            ← always kept whole
      └── Next sub-heading
    Next top-level heading

Algorithm
---------
1. Load CanonicalDocument JSON
2. Re-parse the `content` field into Block objects
3. Walk blocks and accumulate a "current chunk"
4. A new heading triggers: flush current chunk → start new chunk
5. If accumulated words > chunk_max_words: flush at the
   nearest paragraph boundary
6. Tables are always flushed as their own chunk if they would
   exceed max_words, otherwise appended to current chunk

Every chunk carries:
- chunk_id       (document_id + 4-digit index)
- document_id
- chunk_index
- title          (document title)
- heading        (nearest ancestor heading text)
- content        (Markdown text of the chunk)
- url
- metadata       {source_type, page_number, word_count, depth}

Output files: processed_chunks/chunk_NNNNNN.json
Index file  : processed_chunks/index.json
"""

from __future__ import annotations

import json
import time
import traceback
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .config import IngestionConfig, DEFAULT_CONFIG
from .parser import (
    Block, BlockType, HeadingBlock, TableBlock,
    parse_markdown, blocks_to_text,
)
from .utils import (
    setup_logger, log_event, FailedRegistry,
    make_chunk_id, content_hash, clean_text,
    safe_json_load, safe_json_dump, count_words,
)


# ─────────────────────────────────────────────────────────────────────────────
# Chunk dataclass
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Chunk:
    chunk_id: str
    document_id: str
    chunk_index: int
    title: str
    heading: str
    content: str
    url: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def word_count(self) -> int:
        return count_words(self.content)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def save(self, out_dir: Path, global_index: int) -> Path:
        path = out_dir / f"chunk_{global_index:06d}.json"
        safe_json_dump(self.to_dict(), path)
        return path


# ─────────────────────────────────────────────────────────────────────────────
# Chunk assembler
# ─────────────────────────────────────────────────────────────────────────────

class _ChunkAssembler:
    """
    Stateful assembler that walks blocks and emits Chunk objects.
    """

    def __init__(
        self,
        document_id: str,
        title: str,
        url: str,
        source_type: str,
        depth: int,
        max_words: int,
        min_words: int,
    ) -> None:
        self._doc_id     = document_id
        self._title      = title
        self._url        = url
        self._src_type   = source_type
        self._depth      = depth
        self._max_words  = max_words
        self._min_words  = min_words

        self._chunks: list[Chunk] = []
        self._idx: int = 0

        # Current accumulation state
        self._current_heading: str = ""
        self._current_blocks: list[Block] = []
        self._current_words: int = 0

    # ── Public ───────────────────────────────────────────────────────────

    def feed(self, block: Block) -> None:
        """Feed one block into the assembler."""
        btype = block.type
        bwords = block.word_count()

        # ── Headings: always start a new chunk ───────────────────────────
        if btype == BlockType.HEADING:
            hb: HeadingBlock = block  # type: ignore[assignment]
            # Flush on H1/H2; for H3+ only flush if current chunk is large enough
            if hb.level <= 2 or self._current_words >= self._min_words:
                self._flush()
            self._current_heading = hb.heading_text
            self._current_blocks.append(block)
            self._current_words += bwords
            return

        # ── Tables: keep whole if possible ───────────────────────────────
        if btype == BlockType.TABLE:
            if self._current_words + bwords > self._max_words and self._current_words > 0:
                # Flush current content, then emit table as its own chunk
                self._flush()
                self._current_blocks.append(block)
                self._current_words = bwords
                self._flush()  # table is its own chunk
            else:
                self._current_blocks.append(block)
                self._current_words += bwords
            return

        # ── Dividers: flush ───────────────────────────────────────────────
        if btype == BlockType.DIVIDER:
            if self._current_words >= self._min_words:
                self._flush()
            return

        # ── Paragraphs / Lists / Code ─────────────────────────────────────
        if self._current_words + bwords > self._max_words and self._current_words >= self._min_words:
            # Adding this block would exceed max → flush first
            self._flush()
            # Preserve heading context in the new chunk
            if self._current_heading:
                # Add a soft heading marker so chunk is self-contained
                pass  # heading stored in self._current_heading

        self._current_blocks.append(block)
        self._current_words += bwords

    def finish(self) -> list[Chunk]:
        """Flush any remaining content and return all chunks."""
        self._flush()
        return self._chunks

    # ── Private ──────────────────────────────────────────────────────────

    def _flush(self) -> None:
        """Emit the current accumulation as a Chunk (if non-empty)."""
        if not self._current_blocks:
            return

        text = _blocks_to_chunk_text(self._current_blocks)
        text = _normalise_chunk_text(text)

        if not text.strip() or count_words(text) < 3:
            self._current_blocks = []
            self._current_words  = 0
            return

        chunk_id = make_chunk_id(self._doc_id, self._idx)

        chunk = Chunk(
            chunk_id=chunk_id,
            document_id=self._doc_id,
            chunk_index=self._idx,
            title=self._title,
            heading=self._current_heading,
            content=text,
            url=self._url,
            metadata={
                "source_type": self._src_type,
                "page_number": None,          # page_number not tracked per-chunk
                "word_count":  count_words(text),
                "depth":       self._depth,
                "content_hash": content_hash(text),
            },
        )
        self._chunks.append(chunk)
        self._idx += 1

        self._current_blocks = []
        self._current_words  = 0


# ─────────────────────────────────────────────────────────────────────────────
# Text rendering helpers
# ─────────────────────────────────────────────────────────────────────────────

def _blocks_to_chunk_text(blocks: list[Block]) -> str:
    """
    Render a list of blocks to clean Markdown text.
    Preserves headings, tables, lists, paragraphs, code blocks.
    """
    parts: list[str] = []
    for b in blocks:
        if b.type == BlockType.DIVIDER:
            continue
        parts.append(b.text)
    return "\n\n".join(p for p in parts if p.strip())


def _normalise_chunk_text(text: str) -> str:
    """
    Final normalisation pass on chunk text:
    - Remove duplicate blank lines
    - Strip trailing whitespace
    - Preserve Markdown structure
    """
    import re
    # Trailing whitespace per line
    lines = [l.rstrip() for l in text.splitlines()]
    # Collapse 3+ blank lines → 2
    result = re.sub(r"\n{3,}", "\n\n", "\n".join(lines))
    return result.strip()


# ─────────────────────────────────────────────────────────────────────────────
# Per-document chunker
# ─────────────────────────────────────────────────────────────────────────────

def chunk_document(
    doc: dict[str, Any],
    *,
    max_words: int = 1000,
    min_words: int = 30,
) -> list[Chunk]:
    """
    Given a CanonicalDocument dict, return a list of Chunk objects.
    """
    document_id = doc.get("document_id", "unknown")
    title       = doc.get("title", "")
    url         = doc.get("url", "")
    source_type = doc.get("source_type", "html")
    content     = doc.get("content", "")
    meta        = doc.get("metadata", {})
    depth       = meta.get("depth", 0)

    if not content.strip():
        return []

    blocks = parse_markdown(clean_text(content))

    assembler = _ChunkAssembler(
        document_id=document_id,
        title=title,
        url=url,
        source_type=source_type,
        depth=depth,
        max_words=max_words,
        min_words=min_words,
    )
    for block in blocks:
        assembler.feed(block)

    return assembler.finish()


# ─────────────────────────────────────────────────────────────────────────────
# Main chunk builder
# ─────────────────────────────────────────────────────────────────────────────

def build_chunks(config: IngestionConfig = DEFAULT_CONFIG) -> dict[str, Any]:
    """
    Process all canonical documents and write chunk JSON files.

    Returns a summary dict.
    """
    config.create_all_dirs()
    log = setup_logger("chunk_builder", config.logs_dir / "chunk_builder.log")
    failed = FailedRegistry(config.failed_documents_path)

    log_event(log, "START", "=" * 60)
    log_event(log, "START", "Chunk Builder — West Tripura RAG")
    log_event(log, "START", f"Input : {config.processed_docs_dir.resolve()}")
    log_event(log, "START", f"Output: {config.processed_chunks_dir.resolve()}")
    log_event(log, "START",
              f"Params: min={config.chunk_min_words}w "
              f"target={config.chunk_target_words}w "
              f"max={config.chunk_max_words}w")

    doc_files = sorted(
        f for f in config.processed_docs_dir.glob("*.json")
        if f.name != "index.json"
    )
    log_event(log, "PROCESS", f"Documents to chunk: {len(doc_files)}")

    global_chunk_index = 0
    chunk_index_entries: list[dict[str, Any]] = []

    total_docs   = 0
    total_chunks = 0
    errors       = 0

    for doc_path in doc_files:
        t0 = time.monotonic()
        try:
            doc = safe_json_load(doc_path)
            if doc is None:
                raise ValueError("Failed to parse JSON")

            chunks = chunk_document(
                doc,
                max_words=config.chunk_max_words,
                min_words=config.chunk_min_words,
            )

            for chunk in chunks:
                out_path = chunk.save(config.processed_chunks_dir, global_chunk_index)
                chunk_index_entries.append({
                    "chunk_id":    chunk.chunk_id,
                    "document_id": chunk.document_id,
                    "heading":     chunk.heading,
                    "title":       chunk.title,
                    "url":         chunk.url,
                    "file":        out_path.name,
                    "word_count":  chunk.word_count(),
                })
                global_chunk_index += 1
                total_chunks += 1

            elapsed = time.monotonic() - t0
            total_docs += 1
            log_event(
                log, "SAVE",
                f"{doc_path.stem} → {len(chunks)} chunks in {elapsed:.2f}s",
                doc_id=doc.get("document_id", ""),
            )

        except Exception as exc:
            errors += 1
            failed.record(file=str(doc_path), error=str(exc), stage="chunk_build")
            log_event(log, "ERROR", f"Failed {doc_path.name}: {exc}",
                      level="ERROR", file=str(doc_path))

    # ── Write chunk index ──────────────────────────────────────────────────
    index_path = config.processed_chunks_dir / "index.json"
    safe_json_dump(
        {"total": len(chunk_index_entries), "chunks": chunk_index_entries},
        index_path,
    )

    summary = {
        "documents":    total_docs,
        "total_chunks": total_chunks,
        "errors":       errors,
        "index":        str(index_path),
        "avg_chunks_per_doc": round(total_chunks / max(total_docs, 1), 1),
    }

    log_event(log, "COMPLETE", "=" * 60)
    log_event(log, "COMPLETE", f"Documents processed : {total_docs}")
    log_event(log, "COMPLETE", f"Total chunks        : {total_chunks}")
    log_event(log, "COMPLETE", f"Avg chunks/doc      : {summary['avg_chunks_per_doc']}")
    log_event(log, "COMPLETE", f"Errors              : {errors}")
    log_event(log, "COMPLETE", f"Index               : {index_path}")
    log_event(log, "COMPLETE", "=" * 60)

    return summary
