from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from .chunk_models import Chunk
from .chunk_utils import estimate_tokens, normalize_text, sha256_text, is_table_block, is_list_block, block_text
from .config import DEFAULT_CONFIG
from .utils import safe_json_dump, setup_logger, log_event


@dataclass(slots=True)
class ChunkingConfig:
    input_dir: Path = field(default_factory=lambda: DEFAULT_CONFIG.processed_docs_dir.parent / "parsed_documents")
    output_dir: Path = field(default_factory=lambda: DEFAULT_CONFIG.processed_chunks_dir)
    target_tokens: int = 350
    max_tokens: int = 450
    overlap_tokens: int = 40
    min_chunk_tokens: int = 80
    log_path: Path | None = field(default_factory=lambda: DEFAULT_CONFIG.logs_dir / "semantic_chunker.log")


class SemanticChunker:
    """Build heading-aware semantic chunks from parsed document trees."""

    def __init__(self, config: ChunkingConfig | None = None, logger: logging.Logger | None = None) -> None:
        self.config = config or ChunkingConfig()
        self.logger = logger or setup_logger("semantic_chunker", self.config.log_path)
        self.config.output_dir.mkdir(parents=True, exist_ok=True)
        if self.config.log_path is not None:
            self.config.log_path.parent.mkdir(parents=True, exist_ok=True)

    def process_directory(self) -> dict[str, Any]:
        if not self.config.input_dir.exists():
            raise FileNotFoundError(f"Input directory does not exist: {self.config.input_dir}")

        files = sorted(self.config.input_dir.glob("*.json"))
        log_event(self.logger, "START", f"Processing {len(files)} parsed documents from {self.config.input_dir}")
        chunks_written = 0
        chunk_count_total = 0
        token_total = 0
        table_chunks = 0
        list_chunks = 0
        for path in files:
            if path.name == "index.json":
                continue
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                chunks = self.chunk_document(payload, source_path=path.name)
                for chunk in chunks:
                    out_path = self.config.output_dir / f"chunk_{chunks_written + 1:06d}.json"
                    safe_json_dump(chunk.to_dict(), out_path)
                    chunks_written += 1
                    chunk_count_total += 1
                    token_total += chunk.token_count
                    if chunk.has_table:
                        table_chunks += 1
                    if chunk.has_list:
                        list_chunks += 1
            except Exception as exc:  # pragma: no cover - defensive logging
                log_event(self.logger, "ERROR", f"Failed to process {path.name}: {exc}", level="ERROR")

        summary = {
            "documents": len([p for p in files if p.name != "index.json"]),
            "chunks": chunk_count_total,
            "average_tokens": round(token_total / chunk_count_total, 2) if chunk_count_total else 0,
            "chunks_with_tables": table_chunks,
            "chunks_with_lists": list_chunks,
        }
        log_event(self.logger, "DONE", f"Wrote {chunk_count_total} chunks")
        return summary

    def chunk_document(self, payload: Mapping[str, Any], *, source_path: str | None = None) -> list[Chunk]:
        document_id = str(payload.get("document_id") or source_path or "document")
        title = str(payload.get("title") or "Untitled Document")
        metadata = dict(payload.get("metadata") or {})
        tree = payload.get("tree") or {}
        url = str(metadata.get("url") or metadata.get("source_path") or "")
        language = str(metadata.get("language") or "unknown")
        blocks = self._collect_blocks(tree)
        chunks: list[Chunk] = []
        buffer: list[dict[str, Any]] = []
        current_heading_chain: list[str] = []

        for block in blocks:
            block_heading_chain = list(block.get("heading_chain", []))
            if block_heading_chain:
                current_heading_chain = block_heading_chain
            if block.get("type") in {"table", "list"}:
                if buffer:
                    chunks.extend(self._flush_buffer(buffer, document_id=document_id, title=title, url=url, language=language, heading_chain=current_heading_chain))
                    buffer = []
                chunks.append(self._make_chunk({
                    "text": block.get("text") or "",
                    "heading_chain": current_heading_chain,
                    "section": current_heading_chain[-1] if current_heading_chain else "",
                    "sub_section": current_heading_chain[-2] if len(current_heading_chain) > 1 else "",
                    "has_table": is_table_block({"type": block.get("type")}),
                    "has_list": is_list_block({"type": block.get("type")}),
                }, document_id=document_id, title=title, url=url, language=language))
                continue
            if block.get("type") == "paragraph":
                buffer.append(block)
                continue
            if block.get("type") in {"blockquote", "code_block"}:
                if buffer:
                    chunks.extend(self._flush_buffer(buffer, document_id=document_id, title=title, url=url, language=language, heading_chain=current_heading_chain))
                    buffer = []
                chunks.append(self._make_chunk({
                    "text": block.get("text") or "",
                    "heading_chain": current_heading_chain,
                    "section": current_heading_chain[-1] if current_heading_chain else "",
                    "sub_section": current_heading_chain[-2] if len(current_heading_chain) > 1 else "",
                    "has_table": False,
                    "has_list": False,
                }, document_id=document_id, title=title, url=url, language=language))
                continue
        if buffer:
            chunks.extend(self._flush_buffer(buffer, document_id=document_id, title=title, url=url, language=language, heading_chain=current_heading_chain))
        return chunks

    def _collect_blocks(self, node: Mapping[str, Any], *, heading_chain: list[str] | None = None) -> list[dict[str, Any]]:
        heading_chain = list(heading_chain or [])
        blocks: list[dict[str, Any]] = []
        node_type = node.get("type")
        if node_type == "heading":
            heading_chain = heading_chain + [str(node.get("title") or "")]
        if node_type in {"paragraph", "list", "table", "blockquote", "code_block"}:
            blocks.append({
                "type": node_type,
                "text": block_text(node),
                "heading_chain": list(heading_chain),
            })
            return blocks
        for child in node.get("children", []):
            blocks.extend(self._collect_blocks(child, heading_chain=heading_chain))
        return blocks

    def _flush_buffer(self, buffer: list[dict[str, Any]], *, document_id: str, title: str, url: str, language: str, heading_chain: list[str]) -> list[Chunk]:
        text = normalize_text("\n\n".join(block.get("text") or "" for block in buffer if block.get("text")))
        if not text:
            return []
        token_count = estimate_tokens(text)
        if token_count < self.config.min_chunk_tokens:
            return []
        chunk = self._make_chunk({
            "text": text,
            "heading_chain": heading_chain,
            "section": heading_chain[-1] if heading_chain else "",
            "sub_section": heading_chain[-2] if len(heading_chain) > 1 else "",
            "has_table": False,
            "has_list": False,
        }, document_id=document_id, title=title, url=url, language=language)
        return [chunk]

    def _make_chunk(self, section: Mapping[str, Any], *, document_id: str, title: str, url: str, language: str) -> Chunk:
        text = normalize_text(str(section.get("text") or ""))
        token_count = estimate_tokens(text)
        heading_chain = [h for h in section.get("heading_chain", []) if h]
        section_title = heading_chain[-1] if heading_chain else ""
        sub_section = heading_chain[-2] if len(heading_chain) > 1 else ""
        chunk = Chunk(
            text=text,
            heading_chain=heading_chain,
            section=section_title,
            sub_section=sub_section,
            document_id=document_id,
            chunk_index=0,
            total_chunks=1,
            url=url,
            title=title,
            language=language,
            content_type="semantic_chunk",
            token_count=token_count,
            character_count=len(text),
            has_table=bool(section.get("has_table")),
            has_list=bool(section.get("has_list")),
            sha256=sha256_text(text),
        )
        return chunk


def build_chunks(input_dir: str | Path | None = None, output_dir: str | Path | None = None) -> dict[str, Any]:
    config = ChunkingConfig(input_dir=Path(input_dir or DEFAULT_CONFIG.processed_docs_dir.parent / "parsed_documents"), output_dir=Path(output_dir or DEFAULT_CONFIG.processed_chunks_dir))
    chunker = SemanticChunker(config=config)
    return chunker.process_directory()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Build semantic chunks from parsed document trees")
    parser.add_argument("--input-dir", default="parsed_documents", help="Directory containing parsed document tree JSON")
    parser.add_argument("--output-dir", default="processed_chunks", help="Output directory for semantic chunks")
    args = parser.parse_args()
    result = build_chunks(args.input_dir, args.output_dir)
    print(json.dumps(result, indent=2, ensure_ascii=False))
