"""
ingestion/production_chunker.py
===============================
Production-grade semantic chunker for government RAG pipelines.

Philosophy
----------
Chunks are built from the document's *structural hierarchy*, NOT by
token count. The hierarchy respected is:

    Heading H1
      └── Paragraph / List / Table / Code
      └── Heading H2
            └── Paragraph / List / Table / Code
            └── Heading H3
                  └── ...

Rules
-----
1. Every chunk inherits its complete heading chain.
2. Chunks are flushed on H1/H2 boundaries (major section breaks).
3. Oversized paragraphs are split at sentence boundaries via spaCy.
4. Tables, lists, numbered procedures are kept as single units.
5. Overlap between consecutive chunks uses complete sentences only.
6. Token target: 500–600 | max: 700 | min: 100 (tiktoken cl100k_base).

Input:  processed_documents/<document_id>.json   (PreprocessedDocument or CanonicalDocument)
Output: processed_chunks/chunk_NNNNNN.json        (one file per chunk)
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
import unicodedata
from datetime import datetime, timezone
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import tiktoken

from .chunk_models import Chunk
from .config import DEFAULT_CONFIG
from .parser import (
    Block, BlockType, HeadingBlock, TableBlock, ListBlock,
    CodeBlock, ParagraphBlock, parse_markdown,
)
from .utils import setup_logger, log_event, safe_json_dump, detect_language

# ─────────────────────────────────────────────────────────────────────────────
# Tokenizer
# ─────────────────────────────────────────────────────────────────────────────

_TOKENIZER = tiktoken.get_encoding("cl100k_base")


def _estimate_tokens(text: str) -> int:
    if not text.strip():
        return 0
    return len(_TOKENIZER.encode(text))


# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ProductionChunkerConfig:
    target_tokens: int = 550
    max_tokens: int = 700
    min_tokens: int = 100
    overlap_tokens: int = 60
    input_dir: Path = field(default_factory=lambda: DEFAULT_CONFIG.processed_docs_dir)
    output_dir: Path = field(default_factory=lambda: DEFAULT_CONFIG.processed_chunks_dir)
    logs_dir: Path = field(default_factory=lambda: DEFAULT_CONFIG.logs_dir)
    log_path: Path | None = None
    spaCy_model: str = "en_core_web_sm"

    def __post_init__(self) -> None:
        if self.log_path is None:
            self.log_path = self.logs_dir / "production_chunker.log"


# ─────────────────────────────────────────────────────────────────────────────
# Content Cleaner
# ─────────────────────────────────────────────────────────────────────────────

_NAV_PATTERNS: list[re.Pattern] = [
    # Skip-to-content links
    re.compile(r'\[\s*\]\([^)]*#[Ss]kip[Cc]ontent[^)]*\)\s*"Skip to main content"', re.IGNORECASE),
    re.compile(r'\[\s*\]\([^)]*#[Ss]kip[Cc]ontent[^)]*\)', re.IGNORECASE),
    re.compile(r'\[.*?সরাসরি মূল কন্টেন্টে.*?\]\(.*?\)'),
    # Search bars
    re.compile(r'^[\*\- ]*Search\s+Search', re.MULTILINE | re.IGNORECASE),
    re.compile(r'^[\*\- ]*অনুসন্ধান\s+অনুসন্ধান', re.MULTILINE),
    # Social media + sitemap links
    re.compile(r'\[\s*Social Media Links\s*\]', re.IGNORECASE),
    re.compile(r'\[\s*Site Map\s*\]', re.IGNORECASE),
    re.compile(r'\[\s*সাইট ম্যাপ\s*\]'),
    re.compile(r'\[\s*সামাজিক মিডিয়া লিঙ্ক\s*\]'),
    # Bengali accessibility lines
    re.compile(r'^(?:[\*\- ]*)?(?:ফন্ট সাইজ|নর্মাল ফন্ট|'
               r'ফন্ট সাইজ বৃদ্ধি|ফন্ট সাইজ হ্রাস)'
               r'.*$', re.MULTILINE),
    # Accessibility individual lines (with or without * prefix)
    re.compile(
        r'^(?:[\*\- ]*)?(?:High Contrast|Normal Contrast|'
        r'Highlight Links|Invert|Saturation|Font Size Increase|'
        r'Normal Font|Font Size Decrease|Text Spacing|Line Height|'
        r'Big Cursor|Hide Image|Hide images|Show images|'
        r'Color Contrast|Other Controls|Text Size)'
        r'.*$', re.MULTILINE | re.IGNORECASE,
    ),
    # Accessibility header line
    re.compile(r'^\s*Accessibility Tools\s*$', re.MULTILINE | re.IGNORECASE),
    # More Menu navigation heading
    re.compile(r'^#+\s+More Menu\s*$', re.MULTILINE | re.IGNORECASE),

    # Language switcher links
    re.compile(r'^[\*\- ]*\[.*?\]\(.*?\)\s*"[^"]*"$', re.MULTILINE),
    re.compile(r'^[\*\- ]*\[.*?\]\(.*?\)\s*$', re.MULTILINE),
    # Empty image links and back-to-top
    re.compile(r'!\[.*back2top.*\]\(.*\)'),
    re.compile(r'!\[.*bar\d?\.gif.*\]\(.*\)'),
    re.compile(r'!\[.*logo.*\]\(.*\)', re.IGNORECASE),
    re.compile(r'^\s*!\[.*\]\(.*\)\s*$', re.MULTILINE),
    re.compile(r'\[!\[.*\]\(.*\)\]\(.*\)'),
    # Empty links [](url) → leaves bare URL in parens
    re.compile(r'\[\s*\]\([^)]*\)\s*'),
    re.compile(r'\(https?://[^)]*\)'),
    # Government header bar
    re.compile(r'\[\s*Government of State Name .*?\]\(.*?\)'),
    # Footer / copyright
    re.compile(
        r'(?:Content Owned by.*$|Developed and hosted by.*$|'
        r'Hosted by NIC.*$|'
        r'Copyright.*$|©|Disclaimer.*$|Privacy Policy.*$|'
        r'Terms & Conditions.*$|'
        r'Last Updated:.*$|সর্বশেষ সংষ্করণ:.*$)',
        re.IGNORECASE | re.MULTILINE,
    ),
    # Server Error / 404
    re.compile(r'^#\s*Server\s*Error', re.MULTILINE | re.IGNORECASE),
    re.compile(r'^##\s*404\s*-', re.MULTILINE | re.IGNORECASE),
    # Empty table rows
    re.compile(r'^\|[\|\s\-:]+\|$', re.MULTILINE),
    # Standalone pipe artifacts
    re.compile(r'^\|[\s\[\]\(\)\w\d\s\.\/\-\_]+\|$', re.MULTILINE),
]


class ContentCleaner:
    """Strip navigation, accessibility widgets, headers, and footers from markdown."""

    @staticmethod
    def strip_frontmatter(text: str) -> str:
        if text.startswith("---"):
            parts = text.split("---", 2)
            if len(parts) >= 3:
                return parts[2].strip()
        return text.strip()

    @classmethod
    def clean(cls, text: str) -> str:
        text = unicodedata.normalize("NFC", text)
        text = cls.strip_frontmatter(text)
        for pattern in _NAV_PATTERNS:
            text = pattern.sub("", text)
        # Strip everything before the first substantive content heading
        text = cls._strip_pre_content(text)
        lines = text.splitlines()
        cleaned: list[str] = []
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            if stripped in ("*", "-", "**", "***", "|", "||"):
                continue
            if re.match(r'^[\*\-]\s*$', stripped):
                continue
            if re.match(r'^\*$', stripped):
                continue
            if re.match(r'^\(https?://[^)]*\)$', stripped):
                continue
            cleaned.append(stripped)
        text = "\n".join(cleaned)
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r"[ \t]{2,}", " ", text)
        text = re.sub(r"(?m)^\s*\*\s*$", "", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r"[ \t]{2,}", " ", text)
        return text.strip()

    @staticmethod
    def _strip_pre_content(text: str) -> str:
        lines = text.splitlines()
        content_start = 0
        for i, line in enumerate(lines):
            stripped = line.strip()
            if re.match(r'^#{1,2}\s+(?!More Menu|Home|Skip|Search)', stripped, re.IGNORECASE):
                content_start = i
                break
        if content_start > 0:
            return "\n".join(lines[content_start:])
        return text


# ─────────────────────────────────────────────────────────────────────────────
# Sentence Splitter
# ─────────────────────────────────────────────────────────────────────────────

class SentenceSplitter:
    """Sentence-aware text segmentation using spaCy."""

    def __init__(self, model_name: str = "en_core_web_sm") -> None:
        self._nlp: Any = None
        self._model_name = model_name
        self._lazy_load()

    def _lazy_load(self) -> None:
        if self._nlp is None:
            import spacy
            try:
                self._nlp = spacy.load(self._model_name)
            except OSError:
                import subprocess, sys as _sys
                subprocess.run(
                    [_sys.executable, "-m", "spacy", "download", self._model_name],
                    capture_output=True,
                )
                self._nlp = spacy.load(self._model_name)
            self._nlp.max_length = 5_000_000

    def split_sentences(self, text: str) -> list[str]:
        self._lazy_load()
        if not text.strip():
            return []
        doc = self._nlp(text[:2_000_000])
        return [sent.text.strip() for sent in doc.sents if sent.text.strip()]

    def group_sentences(self, sentences: list[str], target_tokens: int) -> list[list[str]]:
        groups: list[list[str]] = []
        current: list[str] = []
        current_tokens = 0
        for sent in sentences:
            sent_tokens = _estimate_tokens(sent)
            if current_tokens + sent_tokens > target_tokens and current:
                groups.append(current)
                current = [sent]
                current_tokens = sent_tokens
            else:
                current.append(sent)
                current_tokens += sent_tokens
        if current:
            groups.append(current)
        return groups


# ─────────────────────────────────────────────────────────────────────────────
# Hierarchy Chunker
# ─────────────────────────────────────────────────────────────────────────────

class _BlockAccumulator:
    """Accumulates blocks under a heading chain and flushes on demand."""

    def __init__(
        self,
        heading_chain: list[str],
        target_tokens: int,
        max_tokens: int,
        min_tokens: int,
        overlap_tokens: int,
        splitter: SentenceSplitter,
        document_id: str,
        title: str,
        url: str,
        language: str,
        created_at: str,
    ) -> None:
        self._heading_chain = list(heading_chain)
        self._blocks: list[Block] = []
        self._target_tokens = target_tokens
        self._max_tokens = max_tokens
        self._min_tokens = min_tokens
        self._overlap_tokens = overlap_tokens
        self._splitter = splitter
        self._document_id = document_id
        self._title = title
        self._url = url
        self._language = language
        self._created_at = created_at
        self._overlap_sentences: list[str] = []

    @property
    def current_tokens(self) -> int:
        return _estimate_tokens(self._blocks_to_text())

    def _blocks_to_text(self, blocks: list[Block] | None = None) -> str:
        target = blocks if blocks is not None else self._blocks
        parts: list[str] = []
        for b in target:
            if b.type == BlockType.DIVIDER:
                continue
            parts.append(b.text)
        return "\n\n".join(p for p in parts if p.strip())

    def add_block(self, block: Block) -> None:
        self._blocks.append(block)

    def has_blocks(self) -> bool:
        return len(self._blocks) > 0

    def add_overlap(self, overlap_sentences: list[str]) -> None:
        self._overlap_sentences = list(overlap_sentences)

    def flush(self, chunk_index: int) -> list[Chunk]:
        if not self._blocks:
            return []
        text = self._blocks_to_text()
        if not text.strip():
            self._blocks = []
            return []
        token_count = _estimate_tokens(text)
        if token_count <= self._max_tokens:
            chunk = self._build_chunk(text, chunk_index)
            self._compute_overlap(chunk)
            self._blocks = []
            return [chunk]
        return self._split_blocks(chunk_index)

    @staticmethod
    def _split_table_block(block: Block, max_tok: int) -> list[Block]:
        lines = block.text.splitlines()
        if len(lines) < 3:
            return [block]
        header = lines[:2]
        data = lines[2:]
        result: list[Block] = []
        current_rows: list[str] = []
        for row in data:
            test = "\n".join(header + current_rows + [row])
            if _estimate_tokens(test) > max_tok and current_rows:
                sub_text = "\n".join(header + current_rows)
                result.append(TableBlock(type=BlockType.TABLE, text=sub_text,
                                         position=block.position))
                current_rows = [row]
            else:
                current_rows.append(row)
        if current_rows:
            sub_text = "\n".join(header + current_rows)
            result.append(TableBlock(type=BlockType.TABLE, text=sub_text,
                                     position=block.position))
        return result if result else [block]

    @staticmethod
    def _split_list_block(block: Block, max_tok: int) -> list[Block]:
        lines = block.text.splitlines()
        result: list[Block] = []
        current: list[str] = []
        for line in lines:
            if not line.strip():
                current.append(line)
                continue
            test = "\n".join(current + [line])
            if _estimate_tokens(test) > max_tok and current:
                result.append(ListBlock(type=BlockType.LIST, text="\n".join(current),
                                       position=block.position))
                current = [line]
            else:
                current.append(line)
        if current:
            result.append(ListBlock(type=BlockType.LIST, text="\n".join(current),
                                   position=block.position))
        return result if result else [block]

    def _split_blocks(self, chunk_index: int) -> list[Chunk]:
        chunks: list[Chunk] = []
        buffer_blocks: list[Block] = []
        buffer_tokens = 0

        for block in self._blocks:
            block_text = block.text.strip()
            block_tokens = _estimate_tokens(block_text)
            should_keep_together = block.type in {
                BlockType.TABLE, BlockType.LIST, BlockType.CODE,
            }

            if should_keep_together:
                # If block itself is huge, force split it
                if block_tokens > self._max_tokens:
                    # Flush existing buffer first
                    if buffer_blocks:
                        c = self._build_chunk(self._blocks_to_text(buffer_blocks), chunk_index)
                        self._compute_overlap(c)
                        chunks.append(c)
                        chunk_index += 1
                        buffer_blocks = []
                        buffer_tokens = 0
                    
                    # Split the massive block
                    if block.type == BlockType.TABLE:
                        subs = self._split_table_block(block, self._max_tokens)
                    elif block.type == BlockType.LIST:
                        subs = self._split_list_block(block, self._max_tokens)
                    else:
                        subs = [block]
                    
                    # Add parts
                    for sb in subs:
                        c = self._build_chunk(sb.text, chunk_index)
                        self._compute_overlap(c)
                        chunks.append(c)
                        chunk_index += 1
                    continue

                # Normal keep-together block
                if buffer_blocks and buffer_tokens + block_tokens > self._max_tokens:
                    c = self._build_chunk(self._blocks_to_text(buffer_blocks), chunk_index)
                    self._compute_overlap(c)
                    chunks.append(c)
                    chunk_index += 1
                    buffer_blocks = []
                    buffer_tokens = 0
                buffer_blocks.append(block)
                buffer_tokens += block_tokens
                continue

            if buffer_tokens + block_tokens > self._max_tokens and buffer_blocks:
                c = self._build_chunk(self._blocks_to_text(buffer_blocks), chunk_index)
                self._compute_overlap(c)
                chunks.append(c)
                chunk_index += 1
                buffer_blocks = []
                buffer_tokens = 0

            if block_tokens > self._target_tokens:
                has_split = True
                sentences = self._splitter.split_sentences(block_text)
                sent_groups = self._splitter.group_sentences(sentences, self._target_tokens)
                for group in sent_groups:
                    group_text = " ".join(group)
                    group_block = ParagraphBlock(
                        type=BlockType.PARAGRAPH,
                        text=group_text,
                        position=block.position,
                    )
                    buffer_blocks.append(group_block)
                    buffer_tokens += _estimate_tokens(group_text)
                    if buffer_tokens >= self._target_tokens:
                        c = self._build_chunk(self._blocks_to_text(buffer_blocks), chunk_index)
                        self._compute_overlap(c)
                        chunks.append(c)
                        chunk_index += 1
                        buffer_blocks = []
                        buffer_tokens = 0
            else:
                buffer_blocks.append(block)
                buffer_tokens += block_tokens

        if buffer_blocks:
            c = self._build_chunk(self._blocks_to_text(buffer_blocks), chunk_index)
            self._compute_overlap(c)
            chunks.append(c)

        self._blocks = []
        return chunks

    def _compute_overlap(self, chunk: Chunk) -> None:
        text = chunk.text
        sentences = self._splitter.split_sentences(text)
        overlap_sents: list[str] = []
        overlap_tok = 0
        for sent in reversed(sentences):
            s_tok = _estimate_tokens(sent)
            if overlap_tok + s_tok > self._overlap_tokens:
                break
            overlap_sents.insert(0, sent)
            overlap_tok += s_tok
        self._overlap_sentences = overlap_sents

    def get_overlap_sentences(self) -> list[str]:
        return list(self._overlap_sentences)

    def _extract_heading_chain(self) -> list[str]:
        chain = [h for h in self._heading_chain if h]
        seen = set(chain)
        for b in self._blocks:
            if b.type == BlockType.HEADING:
                hb: HeadingBlock = b
                text = hb.heading_text.strip()
                if not text or text in seen:
                    continue
                seen.add(text)
                chain.append(text)
        return chain

    def _build_chunk(self, text: str, chunk_index: int) -> Chunk:
        token_count = _estimate_tokens(text)
        heading_chain = self._extract_heading_chain()
        if not heading_chain:
            heading_chain = [h for h in self._heading_chain if h]
        if not heading_chain and self._title:
            heading_chain = [self._title]
        section = heading_chain[0] if heading_chain else ""
        sub_section = heading_chain[-1] if len(heading_chain) > 1 else ""
        has_table = any(b.type == BlockType.TABLE for b in self._blocks)
        has_list = any(b.type == BlockType.LIST for b in self._blocks)
        chunk_id = f"{self._document_id}__chunk_{chunk_index:04d}"
        return Chunk(
            chunk_id=chunk_id,
            text=text,
            heading_chain=heading_chain,
            section=section,
            sub_section=sub_section,
            document_id=self._document_id,
            parent_document=self._document_id,
            chunk_index=chunk_index,
            total_chunks=0,
            previous_chunk_id="",
            next_chunk_id="",
            url=self._url,
            title=self._title,
            language=self._language,
            content_type="semantic_chunk",
            token_count=token_count,
            character_count=len(text),
            has_table=has_table,
            has_list=has_list,
            created_at=self._created_at,
            sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        )


class HierarchyChunker:
    """Build chunks respecting Markdown heading hierarchy."""

    def __init__(
        self,
        target_tokens: int = 550,
        max_tokens: int = 700,
        min_tokens: int = 100,
        overlap_tokens: int = 60,
        splitter: SentenceSplitter | None = None,
    ) -> None:
        self._target_tokens = target_tokens
        self._max_tokens = max_tokens
        self._min_tokens = min_tokens
        self._overlap_tokens = overlap_tokens
        self._splitter = splitter or SentenceSplitter()

    def chunk_blocks(
        self,
        blocks: list[Block],
        document_id: str,
        title: str,
        url: str,
        language: str,
        created_at: str,
    ) -> list[Chunk]:
        if not blocks:
            return []
        heading_chain: list[str] = []
        accumulators: list[_BlockAccumulator] = []
        current: _BlockAccumulator | None = None

        def _make_accumulator() -> _BlockAccumulator:
            return _BlockAccumulator(
                heading_chain=list(heading_chain),
                target_tokens=self._target_tokens,
                max_tokens=self._max_tokens,
                min_tokens=self._min_tokens,
                overlap_tokens=self._overlap_tokens,
                splitter=self._splitter,
                document_id=document_id,
                title=title,
                url=url,
                language=language,
                created_at=created_at,
            )

        for block in blocks:
            if block.type == BlockType.HEADING:
                hb: HeadingBlock = block
                if hb.level <= 2:
                    if current and current.has_blocks():
                        accumulators.append(current)
                    heading_chain = self._update_heading_chain(heading_chain, hb)
                    current = _make_accumulator()
                else:
                    heading_chain = self._update_heading_chain(heading_chain, hb)
                    if current is None:
                        current = _make_accumulator()
                current.add_block(block)
                continue
            if block.type == BlockType.DIVIDER:
                if current and current.has_blocks() and current.current_tokens >= self._min_tokens:
                    accumulators.append(current)
                    heading_chain = []
                    current = _make_accumulator()
                continue
            if current is None:
                current = _make_accumulator()
            current.add_block(block)

        if current and current.has_blocks():
            accumulators.append(current)

        all_chunks: list[Chunk] = []
        chunk_index = 0
        for acc in accumulators:
            chunks = acc.flush(chunk_index)
            for i, chunk in enumerate(chunks):
                chunk.chunk_index = chunk_index
                all_chunks.append(chunk)
                chunk_index += 1
            overlap_sents = acc.get_overlap_sentences()
            if overlap_sents and all_chunks:
                next_acc_idx = accumulators.index(acc) + 1
                if next_acc_idx < len(accumulators):
                    accumulators[next_acc_idx].add_overlap(overlap_sents)

        final = self._merge_small_chunks(all_chunks)
        for i, chunk in enumerate(final):
            chunk.chunk_index = i
            chunk.chunk_id = f"{chunk.document_id}__chunk_{i:04d}"
        final = self._link_chunks(final)
        for chunk in final:
            chunk.total_chunks = len(final)
        return final

    def _update_heading_chain(self, chain: list[str], heading: HeadingBlock) -> list[str]:
        level = heading.level
        text = heading.heading_text.strip()
        if not text:
            return chain
        new_chain = [h for i, h in enumerate(chain) if i < level - 1]
        new_chain.append(text)
        return new_chain

    def _link_chunks(self, chunks: list[Chunk]) -> list[Chunk]:
        for i, chunk in enumerate(chunks):
            if i > 0:
                chunk.previous_chunk_id = chunks[i - 1].chunk_id
            if i < len(chunks) - 1:
                chunk.next_chunk_id = chunks[i + 1].chunk_id
        return chunks

    @staticmethod
    def _shared_heading_prefix(a: list[str], b: list[str]) -> int:
        count = 0
        for x, y in zip(a, b):
            if x == y:
                count += 1
            else:
                break
        return count

    def _merge_small_chunks(self, chunks: list[Chunk]) -> list[Chunk]:
        if len(chunks) <= 1:
            return chunks
        merged: list[Chunk] = []
        for chunk in chunks:
            if not merged:
                merged.append(chunk)
                continue
            shared = self._shared_heading_prefix(
                merged[-1].heading_chain, chunk.heading_chain
            )
            prev_small = merged[-1].token_count < self._min_tokens
            curr_small = chunk.token_count < self._min_tokens
            fits = merged[-1].token_count + chunk.token_count <= self._max_tokens
            mergeable = shared >= min(len(merged[-1].heading_chain),
                                      len(chunk.heading_chain))

            if mergeable and prev_small and fits:
                prev = merged.pop()
                prev.text = prev.text + "\n\n" + chunk.text
                merged.append(self._rebuild_chunk(prev, chunk))
            elif mergeable and curr_small and fits:
                prev = merged[-1]
                prev.text = prev.text + "\n\n" + chunk.text
                merged[-1] = self._rebuild_chunk(prev, chunk)
            else:
                merged.append(chunk)
        return merged

    def _rebuild_chunk(self, target: Chunk, source: Chunk) -> Chunk:
        tc = list(target.heading_chain)
        sc = list(source.heading_chain)
        common = []
        for a, b in zip(tc, sc):
            if a == b:
                common.append(a)
            else:
                break
        if not common:
            common = tc[:1] if tc else sc[:1] if sc else []
        if max(len(tc), len(sc)) > len(common) and common:
            deeper = tc if len(tc) > len(sc) else sc
            next_h = deeper[len(common)] if len(deeper) > len(common) else None
            if next_h and next_h not in common:
                common.append(next_h)
        text = target.text
        token_count = _estimate_tokens(text)
        target.token_count = token_count
        target.character_count = len(text)
        target.has_table = target.has_table or source.has_table
        target.has_list = target.has_list or source.has_list
        target.section = common[0] if common else ""
        target.sub_section = common[-1] if len(common) > 1 else ""
        target.heading_chain = common
        target.sha256 = hashlib.sha256(text.encode("utf-8")).hexdigest()
        return target


# ─────────────────────────────────────────────────────────────────────────────
# Chunk Writer
# ─────────────────────────────────────────────────────────────────────────────

class ChunkWriter:
    """Write chunk JSON files to the output directory."""

    def __init__(self, output_dir: Path) -> None:
        self._output_dir = output_dir
        self._output_dir.mkdir(parents=True, exist_ok=True)
        self._global_index = 0
        self._index_entries: list[dict[str, Any]] = []

    def write(self, chunk: Chunk) -> Path:
        out_path = self._output_dir / f"chunk_{self._global_index:06d}.json"
        data = chunk.to_dict()
        safe_json_dump(data, out_path)
        self._index_entries.append({
            "chunk_id": chunk.chunk_id,
            "document_id": chunk.document_id,
            "file": out_path.name,
            "chunk_index": chunk.chunk_index,
            "total_chunks": chunk.total_chunks,
            "title": chunk.title,
            "section": chunk.section,
            "url": chunk.url,
            "token_count": chunk.token_count,
        })
        self._global_index += 1
        return out_path

    def write_index(self) -> Path:
        index_path = self._output_dir / "index.json"
        safe_json_dump({
            "total": len(self._index_entries),
            "chunks": self._index_entries,
        }, index_path)
        return index_path

    @property
    def chunk_count(self) -> int:
        return self._global_index


# ─────────────────────────────────────────────────────────────────────────────
# Production Chunker (Orchestrator)
# ─────────────────────────────────────────────────────────────────────────────

class ProductionChunker:
    """Orchestrator: loads documents, cleans, chunks, and writes output."""

    def __init__(
        self,
        config: ProductionChunkerConfig | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self._config = config or ProductionChunkerConfig()
        self._logger = logger or setup_logger(
            "production_chunker",
            self._config.log_path or (self._config.logs_dir / "production_chunker.log"),
        )
        self._splitter = SentenceSplitter(self._config.spaCy_model)
        self._chunker = HierarchyChunker(
            target_tokens=self._config.target_tokens,
            max_tokens=self._config.max_tokens,
            min_tokens=self._config.min_tokens,
            overlap_tokens=self._config.overlap_tokens,
            splitter=self._splitter,
        )

    def process_document(self, doc_path: Path, writer: ChunkWriter) -> int:
        try:
            data = json.loads(doc_path.read_text(encoding="utf-8"))
        except Exception as exc:
            log_event(self._logger, "ERROR", f"Failed to load JSON: {doc_path.name}: {exc}", level="ERROR")
            return 0
        document_id = data.get("document_id") or doc_path.stem
        title = data.get("title") or document_id
        url = data.get("url") or data.get("metadata", {}).get("url", "")
        language = data.get("language") or detect_language(data.get("content", ""))
        created_at = data.get("crawled_at") or datetime.now(timezone.utc).isoformat()
        content = data.get("content", "")
        if not content.strip():
            log_event(self._logger, "SKIP", f"Empty content: {doc_path.name}", level="WARNING")
            return 0
        cleaned_text = ContentCleaner.clean(content)
        if len(cleaned_text.strip()) < 50:
            log_event(self._logger, "SKIP", f"Content too short after cleaning: {doc_path.name}", level="WARNING")
            return 0
        blocks = parse_markdown(cleaned_text)
        if not blocks:
            log_event(self._logger, "SKIP", f"No blocks after parsing: {doc_path.name}", level="WARNING")
            return 0

        chunks = self._chunker.chunk_blocks(
            blocks=blocks,
            document_id=document_id,
            title=title,
            url=url,
            language=language,
            created_at=created_at,
        )
        count = 0
        for chunk in chunks:
            writer.write(chunk)
            count += 1
        return count

    def process_directory(
        self,
        input_dir: Path | None = None,
        output_dir: Path | None = None,
    ) -> dict[str, Any]:
        input_dir = input_dir or self._config.input_dir
        output_dir = output_dir or self._config.output_dir
        if not input_dir.exists():
            raise FileNotFoundError(f"Input directory not found: {input_dir}")

        doc_files = sorted(
            f for f in input_dir.glob("*.json")
            if f.name != "index.json"
        )
        log_event(self._logger, "START", f"Processing {len(doc_files)} documents from {input_dir}")

        writer = ChunkWriter(output_dir)
        total_chunks = 0
        processed = 0
        skipped = 0
        errors = 0
        t0 = time.monotonic()

        for doc_path in doc_files:
            count = self.process_document(doc_path, writer)
            if count > 0:
                processed += 1
                total_chunks += count
                log_event(self._logger, "CHUNKED", f"{doc_path.name} → {count} chunks")
            else:
                skipped += 1

        elapsed = time.monotonic() - t0
        writer.write_index()

        summary = {
            "documents": processed,
            "total_chunks": total_chunks,
            "skipped": skipped,
            "errors": errors,
            "elapsed_s": round(elapsed, 2),
            "avg_chunks_per_doc": round(total_chunks / max(processed, 1), 1),
            "output_dir": str(output_dir.resolve()),
        }

        log_event(self._logger, "DONE", f"Processed {processed} docs → {total_chunks} chunks in {elapsed:.1f}s")
        return summary


# ─────────────────────────────────────────────────────────────────────────────
# Convenience function
# ─────────────────────────────────────────────────────────────────────────────

def run_production_chunker(
    input_dir: str | Path | None = None,
    output_dir: str | Path | None = None,
    target_tokens: int = 550,
    max_tokens: int = 700,
    min_tokens: int = 100,
    overlap_tokens: int = 60,
) -> dict[str, Any]:
    config = ProductionChunkerConfig(
        target_tokens=target_tokens,
        max_tokens=max_tokens,
        min_tokens=min_tokens,
        overlap_tokens=overlap_tokens,
        input_dir=Path(input_dir) if input_dir else DEFAULT_CONFIG.processed_docs_dir,
        output_dir=Path(output_dir) if output_dir else DEFAULT_CONFIG.processed_chunks_dir,
    )
    chunker = ProductionChunker(config=config)
    return chunker.process_directory()


if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        prog="production_chunker",
        description="Production-grade semantic chunker for West Tripura RAG",
    )
    parser.add_argument("--input-dir", default="processed_documents", help="Input document directory")
    parser.add_argument("--output-dir", default="processed_chunks", help="Output chunk directory")
    parser.add_argument("--target-tokens", type=int, default=550, help="Target tokens per chunk")
    parser.add_argument("--max-tokens", type=int, default=700, help="Maximum tokens per chunk")
    parser.add_argument("--min-tokens", type=int, default=100, help="Minimum tokens per chunk")
    parser.add_argument("--overlap-tokens", type=int, default=60, help="Overlap tokens between chunks")
    args = parser.parse_args()

    result = run_production_chunker(
        input_dir=args.input_dir,
        output_dir=args.output_dir,
        target_tokens=args.target_tokens,
        max_tokens=args.max_tokens,
        min_tokens=args.min_tokens,
        overlap_tokens=args.overlap_tokens,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    sys.exit(0)
