"""
Markdown Chunker for Vector Database Ingestion
===============================================
Reads all crawled Markdown files from output/pages/ and splits them
into overlapping chunks suitable for embedding and vector DB ingestion.

Outputs:
  output/chunks.jsonl  – one JSON object per chunk, ready to embed

Chunk format:
  {
    "chunk_id": "...",
    "url": "https://...",
    "depth": 1,
    "chunk_index": 0,
    "total_chunks": 3,
    "text": "... chunk text ...",
    "char_count": 512,
    "crawled_at": "2024-..."
  }

Usage:
  python chunker.py
  python chunker.py --chunk-size 800 --overlap 100
"""

import argparse
import hashlib
import json
import re
from pathlib import Path

OUTPUT_DIR = Path("output")
PAGES_DIR = OUTPUT_DIR / "pages"
CHUNKS_FILE = OUTPUT_DIR / "chunks.jsonl"
MANIFEST_FILE = OUTPUT_DIR / "manifest.jsonl"

DEFAULT_CHUNK_SIZE = 600    # characters per chunk
DEFAULT_OVERLAP = 80        # overlap between consecutive chunks


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────
def parse_frontmatter(text: str) -> tuple[dict, str]:
    """Extract YAML frontmatter (---...---) and return (meta, body)."""
    meta = {}
    body = text
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            for line in parts[1].strip().splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    meta[k.strip()] = v.strip()
            body = parts[2].strip()
    return meta, body


def clean_markdown(text: str) -> str:
    """Light cleanup: collapse blank lines, strip nav-only lines."""
    # Remove lines that are purely separators or very short (< 3 chars)
    lines = [l for l in text.splitlines() if len(l.strip()) >= 3 or l.strip() == ""]
    # Collapse 3+ consecutive blank lines into 2
    result = re.sub(r"\n{3,}", "\n\n", "\n".join(lines))
    return result.strip()


def split_into_chunks(text: str, chunk_size: int, overlap: int) -> list[str]:
    """
    Split text into chunks of approximately chunk_size characters,
    with overlap characters of context overlap between consecutive chunks.
    Tries to break at sentence/paragraph boundaries.
    """
    if not text:
        return []

    chunks = []
    start = 0
    length = len(text)

    while start < length:
        end = min(start + chunk_size, length)

        # Try to find a good break point (paragraph, sentence, word)
        if end < length:
            # Prefer paragraph break
            break_pos = text.rfind("\n\n", start, end)
            if break_pos == -1 or break_pos <= start:
                # Sentence break
                for sep in (". ", "! ", "? ", "\n"):
                    p = text.rfind(sep, start, end)
                    if p > start + chunk_size // 2:
                        break_pos = p + len(sep)
                        break
                else:
                    # Word break
                    p = text.rfind(" ", start, end)
                    break_pos = p if p > start else end
            else:
                break_pos += 2  # skip the \n\n

            end = break_pos if break_pos > start else end

        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)

        start = end - overlap if end - overlap > start else end

    return chunks


def load_manifest() -> dict[str, dict]:
    """Load manifest.jsonl into a dict keyed by file path."""
    meta_by_file = {}
    if MANIFEST_FILE.exists():
        for line in MANIFEST_FILE.read_text(encoding="utf-8").splitlines():
            try:
                entry = json.loads(line)
                meta_by_file[entry["file"]] = entry
            except Exception:
                pass
    return meta_by_file


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────
def main(chunk_size: int = DEFAULT_CHUNK_SIZE, overlap: int = DEFAULT_OVERLAP):
    if not PAGES_DIR.exists():
        print(f"Pages directory not found: {PAGES_DIR}")
        print("Run crawler.py first.")
        return

    md_files = sorted(PAGES_DIR.glob("*.md"))
    if not md_files:
        print("No markdown files found in output/pages/")
        return

    manifest = load_manifest()

    # Wipe previous chunks file
    CHUNKS_FILE.unlink(missing_ok=True)

    total_chunks = 0
    total_files = 0
    skipped = 0

    print(f"Chunking {len(md_files)} markdown files …")
    print(f"  chunk_size={chunk_size} chars | overlap={overlap} chars")
    print(f"  Output: {CHUNKS_FILE.resolve()}")
    print()

    with CHUNKS_FILE.open("w", encoding="utf-8") as out:
        for md_path in md_files:
            raw = md_path.read_text(encoding="utf-8")
            frontmatter, body = parse_frontmatter(raw)
            body = clean_markdown(body)

            if len(body) < 50:   # skip nearly empty pages
                skipped += 1
                continue

            # Metadata from frontmatter or manifest
            rel_path = str(md_path.relative_to(OUTPUT_DIR))
            manifest_entry = manifest.get(rel_path, {})
            url = frontmatter.get("url") or manifest_entry.get("url", "unknown")
            depth = int(frontmatter.get("depth", manifest_entry.get("depth", 0)))
            crawled_at = frontmatter.get("crawled_at") or manifest_entry.get("crawled_at", "")

            chunks = split_into_chunks(body, chunk_size, overlap)
            n_chunks = len(chunks)

            for idx, chunk_text in enumerate(chunks):
                chunk_id = hashlib.md5(
                    f"{url}::{idx}".encode()
                ).hexdigest()

                record = {
                    "chunk_id": chunk_id,
                    "url": url,
                    "depth": depth,
                    "chunk_index": idx,
                    "total_chunks": n_chunks,
                    "text": chunk_text,
                    "char_count": len(chunk_text),
                    "crawled_at": crawled_at,
                    "source_file": rel_path,
                }
                out.write(json.dumps(record, ensure_ascii=False) + "\n")
                total_chunks += 1

            total_files += 1
            if total_files % 50 == 0:
                print(f"  Processed {total_files}/{len(md_files)} files …")

    print()
    print("=" * 50)
    print(f"Done!")
    print(f"  Files processed : {total_files}")
    print(f"  Files skipped   : {skipped} (too short)")
    print(f"  Total chunks    : {total_chunks}")
    print(f"  Output file     : {CHUNKS_FILE.resolve()}")
    print("=" * 50)
    print()
    print("Each line in chunks.jsonl is one chunk ready to embed.")
    print("Load it with:")
    print("  import json")
    print('  chunks = [json.loads(l) for l in open("output/chunks.jsonl")]')


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Chunk crawled Markdown for vector DB ingestion.")
    parser.add_argument("--chunk-size", type=int, default=DEFAULT_CHUNK_SIZE,
                        help=f"Approximate chunk size in characters (default: {DEFAULT_CHUNK_SIZE})")
    parser.add_argument("--overlap", type=int, default=DEFAULT_OVERLAP,
                        help=f"Overlap between chunks in characters (default: {DEFAULT_OVERLAP})")
    args = parser.parse_args()
    main(chunk_size=args.chunk_size, overlap=args.overlap)
