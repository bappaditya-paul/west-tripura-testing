from __future__ import annotations

from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class Chunk:
    text: str
    heading_chain: list[str] = field(default_factory=list)
    section: str = ""
    sub_section: str = ""
    document_id: str = ""
    parent_document: str = ""
    chunk_index: int = 0
    total_chunks: int = 0
    previous_chunk_id: str = ""
    next_chunk_id: str = ""
    chunk_id: str = ""
    url: str = ""
    title: str = ""
    language: str = ""
    content_type: str = "semantic_chunk"
    token_count: int = 0
    character_count: int = 0
    has_table: bool = False
    has_list: bool = False
    created_at: str = ""
    sha256: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "document_id": self.document_id,
            "parent_document": self.parent_document,
            "chunk_index": self.chunk_index,
            "total_chunks": self.total_chunks,
            "previous_chunk_id": self.previous_chunk_id,
            "next_chunk_id": self.next_chunk_id,
            "title": self.title,
            "url": self.url,
            "heading_chain": self.heading_chain,
            "heading": self.section,
            "section": self.section,
            "sub_section": self.sub_section,
            "text": self.text,
            "content": self.text,
            "language": self.language,
            "content_type": self.content_type,
            "token_count": self.token_count,
            "character_count": self.character_count,
            "has_table": self.has_table,
            "has_list": self.has_list,
            "created_at": self.created_at,
            "sha256": self.sha256,
        }
