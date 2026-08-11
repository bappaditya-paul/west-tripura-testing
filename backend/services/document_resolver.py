from __future__ import annotations

import html
import re
from dataclasses import dataclass
from urllib.parse import urlparse


DOCUMENT_EXTENSIONS = {
    ".pdf": "PDF",
    ".doc": "DOC",
    ".docx": "DOCX",
    ".xls": "XLS",
    ".xlsx": "XLSX",
    ".csv": "CSV",
}


@dataclass(frozen=True)
class DocumentLink:
    title: str
    url: str
    document_type: str


def extract_document_links(chunks: list[dict]) -> list[DocumentLink]:
    """Extract downloadable document links mentioned by retrieved content/metadata."""
    found: dict[str, DocumentLink] = {}
    pattern = re.compile(r"https?://[^\s<>\]\[\)\"']+", re.I)

    for chunk in chunks:
        title = html.unescape(str(chunk.get("title") or chunk.get("metadata", {}).get("title") or "West Tripura document"))
        metadata = chunk.get("metadata") or {}
        candidates = [
            metadata.get("document_url"),
            metadata.get("download_url"),
            metadata.get("file_url"),
            chunk.get("document_url"),
            chunk.get("download_url"),
            chunk.get("file_url"),
        ]
        content = str(chunk.get("content") or chunk.get("text") or "")
        candidates.extend(pattern.findall(content))

        for raw_url in candidates:
            if not raw_url:
                continue
            url = str(raw_url).rstrip(".,;)"]}")
            path = urlparse(url).path.lower()
            suffix = next((ext for ext in DOCUMENT_EXTENSIONS if path.endswith(ext)), None)
            if not suffix:
                continue
            found[url] = DocumentLink(
                title=title,
                url=url,
                document_type=DOCUMENT_EXTENSIONS[suffix],
            )

    return list(found.values())


def format_documents(language: str, docs: list[DocumentLink]) -> str:
    if not docs:
        return ""
    if language == "bn":
        heading = "📄 ডাউনলোডযোগ্য নথি"
    elif language == "bn_en":
        heading = "📄 Downloadable documents"
    else:
        heading = "📄 Documents you can download"

    lines = [heading]
    for doc in docs[:5]:
        lines.append(f"- {doc.title} ({doc.document_type}): {doc.url}")
    return "\n".join(lines)
