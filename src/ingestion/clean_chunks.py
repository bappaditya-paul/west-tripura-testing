"""
clean_chunks.py
===============
Step 1 of Chunk Quality Improvement Plan.
Filters out exact duplicates, near-duplicates, server errors, and navigation menu chunks.
Writes clean chunks to clean_chunks/ directory.
"""

import os
import sys
import glob
import json
import hashlib
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent.parent))

from src.ingestion.core.config import PROCESSED_CHUNKS_DIR

CLEAN_CHUNKS_DIR = _HERE.parent.parent / "clean_chunks"

# Filter settings
MIN_TOKENS = 30
ERROR_KEYWORDS = [
    "file or directory not found",
    "server error",
    "404",
    "the resource you are looking for",
    "temporarily unavailable"
]

def get_content(chunk: dict) -> str:
    return (chunk.get("content") or chunk.get("text") or "").strip()

def is_error_page(content: str) -> bool:
    content_lower = content.lower()
    return any(kw in content_lower for kw in ERROR_KEYWORDS)

def is_navigation_chunk(chunk: dict, content: str) -> bool:
    has_table = bool(chunk.get("has_table"))
    has_list = bool(chunk.get("has_list"))
    token_count = chunk.get("token_count", 0)
    
    # Heuristic for navigation menus: low token count, has tables/lists, high ratio of Markdown links
    if has_table and has_list and token_count < 150:
        # Count brackets (indicating Markdown links like [link text]) vs sentences
        link_brackets = content.count("[")
        periods = content.count(".") + content.count("।")
        if link_brackets > periods:
            return True
            
    # Check if the title suggests a generic menu or folder structure
    title = chunk.get("title", "").lower()
    if title in ["more menu", "navigation", "menu", "sitemap"]:
        # If it's mostly links
        if content.count("[") > 5 and content.count(".") < 3:
            return True
            
    return False

def main():
    print("=" * 60)
    print("  STEP 1: CLEAN CHUNKS")
    print("=" * 60)
    
    CLEAN_CHUNKS_DIR.mkdir(parents=True, exist_ok=True)
    
    chunk_files = sorted(PROCESSED_CHUNKS_DIR.glob("chunk_*.json"))
    if not chunk_files:
        print(f"✗ No chunk_*.json files found in {PROCESSED_CHUNKS_DIR}")
        return 1
        
    print(f"Loading {len(chunk_files):,} chunks...")
    
    raw_chunks = []
    for fp in chunk_files:
        try:
            raw_chunks.append(json.loads(fp.read_text("utf-8")))
        except Exception as e:
            print(f"Error loading {fp.name}: {e}")
            
    print(f"Loaded {len(raw_chunks)} chunks.")
    
    seen_hashes = set()
    seen_prefixes = {}  # prefix -> token_count
    
    stats = {
        "raw": len(raw_chunks),
        "exact_dupes": 0,
        "near_dupes": 0,
        "error_pages": 0,
        "navigation": 0,
        "too_small": 0,
        "clean": 0
    }
    
    clean_chunks = []
    
    # We do a two-pass check:
    # Pass 1: Filter out based on content, error pages, navigation, min size, exact hash
    first_pass_candidates = []
    for chunk in raw_chunks:
        content = get_content(chunk)
        tokens = chunk.get("token_count", 0)
        
        # Filter: Too Small
        if tokens < MIN_TOKENS:
            stats["too_small"] += 1
            continue
            
        # Filter: Error pages
        if is_error_page(content):
            stats["error_pages"] += 1
            continue
            
        # Filter: Navigation menus
        if is_navigation_chunk(chunk, content):
            stats["navigation"] += 1
            continue
            
        # Filter: Exact duplicate content
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        if content_hash in seen_hashes:
            stats["exact_dupes"] += 1
            continue
            
        seen_hashes.add(content_hash)
        first_pass_candidates.append(chunk)
        
    # Pass 2: Filter near-duplicates based on prefix of content
    # Sort candidates by token count descending so we keep the more detailed chunk if prefixes match
    first_pass_candidates.sort(key=lambda x: x.get("token_count", 0), reverse=True)
    
    for chunk in first_pass_candidates:
        content = get_content(chunk)
        prefix = content[:150].strip().lower()
        
        if not prefix:
            continue
            
        # If we've seen this exact prefix before, it's a near duplicate
        if prefix in seen_prefixes:
            stats["near_dupes"] += 1
            continue
            
        seen_prefixes[prefix] = chunk.get("token_count", 0)
        clean_chunks.append(chunk)
        
    # Sort back by chunk_index / chunk_id
    clean_chunks.sort(key=lambda x: x.get("chunk_id", ""))
    
    # Save the cleaned chunks
    # Clean output dir first
    for f in CLEAN_CHUNKS_DIR.glob("chunk_*.json"):
        f.unlink()
        
    for i, chunk in enumerate(clean_chunks):
        out_fp = CLEAN_CHUNKS_DIR / f"chunk_{i:06d}.json"
        out_fp.write_text(json.dumps(chunk, indent=2, ensure_ascii=False), "utf-8")
        
    stats["clean"] = len(clean_chunks)
    
    print("\n" + "─" * 60)
    print("  CLEANING REPORT")
    print("─" * 60)
    print(f"  Raw chunks          : {stats['raw']:>5,}")
    print(f"  Below min tokens    : {stats['too_small']:>5,}")
    print(f"  Error pages         : {stats['error_pages']:>5,}")
    print(f"  Navigation/Menu     : {stats['navigation']:>5,}")
    print(f"  Exact duplicates    : {stats['exact_dupes']:>5,}")
    print(f"  Near duplicates     : {stats['near_dupes']:>5,}")
    print(f"  ─────────────────────────")
    print(f"  Clean chunks written: {stats['clean']:>5,}")
    print("=" * 60)
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
