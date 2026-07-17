"""
embed_and_load.py
=================
Production-grade embedding + Pinecone ingestion in a single pass.

Reads chunks from processed_chunks/, filters out low-quality entries,
embeds with NVIDIA NV-Embed-v1 (cloud API, 4096-dim, cosine), and
upserts directly to Pinecone index 'west-tripura-chatbot'.

Usage:
    python embed_and_load.py                        # full run
    python embed_and_load.py --dry-run              # test API + print first batch
    python embed_and_load.py --min-tokens 50        # stricter filter
    python embed_and_load.py --embed-batch 8        # smaller API batch
    python embed_and_load.py --pinecone-batch 100   # upsert batch size
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent.parent))

# Load .env before importing config
try:
    from dotenv import load_dotenv
    load_dotenv(_HERE.parent.parent / ".env")
except ImportError:
    pass

from src.ingestion.core.config import (
    PROCESSED_CHUNKS_DIR,
    NV_API_KEY,
    NV_API_BASE_URL,
    NV_EMBED_MODEL,
    VECTOR_SIZE,
    PINECONE_API_KEY,
    PINECONE_INDEX_NAME,
    PINECONE_HOST,
    EMBED_BATCH_SIZE,
    BATCH_SIZE,
)


# ── Constants ─────────────────────────────────────────────────────────────────

MAX_EMBED_CHARS    = 2048   # NV-Embed supports up to 512 tokens; cap chars generously
MIN_EMBED_CHARS    = 20
DEFAULT_MIN_TOKENS = 30
DEFAULT_EMBED_BATCH = EMBED_BATCH_SIZE   # from config (default 16)
DEFAULT_PC_BATCH    = BATCH_SIZE         # from config (default 96)


# ── Text preparation ──────────────────────────────────────────────────────────

_IMG_MD_RE       = re.compile(r"!\[.*?\]\(.*?\)")
_IMG_HTML_RE     = re.compile(r"<img[^>]*>", re.IGNORECASE)
_CTRL_RE         = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_LINK_RE         = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_MD_LINK_ONLY_RE = re.compile(r"^(\s*\*\s*\[\s*\]\(\S+\)\s*\n?)+$")


def _prepare_text(chunk: dict) -> str:
    """Build a clean, embedding-ready string from a chunk dict."""
    heading_chain = chunk.get("heading_chain") or []
    if not heading_chain:
        h = chunk.get("heading", "")
        if h:
            heading_chain = [h]

    parts: list[str] = []
    if heading_chain:
        parts.append(" > ".join(heading_chain))

    title = chunk.get("title", "").strip()
    if title and title not in heading_chain:
        parts.append(title)

    content = (chunk.get("content") or chunk.get("text") or "").strip()
    if content:
        content = _IMG_MD_RE.sub("", content)
        content = _IMG_HTML_RE.sub("", content)
        content = _CTRL_RE.sub("", content)
        content = _LINK_RE.sub(r"\1", content)
        content = content.strip()
        if _MD_LINK_ONLY_RE.match(content):
            return ""
        if len(content) > MAX_EMBED_CHARS:
            content = content[:MAX_EMBED_CHARS]
            last_space = content.rfind(" ")
            if last_space > MAX_EMBED_CHARS * 0.8:
                content = content[:last_space]
        parts.append(content)

    return "\n\n".join(p for p in parts if p)


# ── Stable vector ID ──────────────────────────────────────────────────────────

def _vector_id(chunk_id: str) -> str:
    """Pinecone uses string IDs — use SHA-256 hex of chunk_id."""
    return hashlib.sha256(chunk_id.encode("utf-8")).hexdigest()


# ── Payload builder ───────────────────────────────────────────────────────────

def _build_payload(chunk: dict) -> dict[str, Any]:
    heading_chain = chunk.get("heading_chain") or []
    section    = heading_chain[0] if heading_chain else ""
    subsection = heading_chain[-1] if len(heading_chain) > 1 else ""

    payload: dict[str, Any] = {
        "chunk_id":      chunk.get("chunk_id", ""),
        "document_id":   chunk.get("document_id", ""),
        "title":         chunk.get("title", ""),
        "url":           chunk.get("url", ""),
        "section":       section,
        "sub_section":   subsection,
        "heading_chain": heading_chain,
        "language":      chunk.get("language", "unknown"),
        "has_table":     bool(chunk.get("has_table")),
        "has_list":      bool(chunk.get("has_list")),
        "chunk_index":   chunk.get("chunk_index", 0),
        "total_chunks":  chunk.get("total_chunks", 0),
        "token_count":   chunk.get("token_count", 0),
        "content":       (chunk.get("content") or chunk.get("text") or ""),
    }
    # Remove None and empty-string values (Pinecone is strict)
    return {k: v for k, v in payload.items() if v is not None and v != ""}


# ── NVIDIA NV-Embed API ───────────────────────────────────────────────────────

def _embed_batch(texts: list[str], api_key: str, *, input_type: str = "passage") -> list[list[float]]:
    """
    Call NVIDIA NV-Embed-v1 API for a batch of texts.
    Returns list of 4096-dim float vectors.
    """
    from openai import OpenAI

    client = OpenAI(
        api_key=api_key,
        base_url=NV_API_BASE_URL,
    )

    response = client.embeddings.create(
        model=NV_EMBED_MODEL,
        input=texts,
        extra_body={"input_type": input_type, "truncate": "END"},
        encoding_format="float",
    )

    # Sort by index to ensure order
    data = sorted(response.data, key=lambda x: x.index)
    return [item.embedding for item in data]


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Embed chunks with NVIDIA NV-Embed-v1 → upsert to Pinecone"
    )
    parser.add_argument("--chunks-dir",     type=Path, default=PROCESSED_CHUNKS_DIR,
                        help="Directory containing chunk_*.json files")
    parser.add_argument("--min-tokens",     type=int,  default=DEFAULT_MIN_TOKENS,
                        help=f"Skip chunks below this token count (default: {DEFAULT_MIN_TOKENS})")
    parser.add_argument("--embed-batch",    type=int,  default=DEFAULT_EMBED_BATCH,
                        help=f"Texts per NVIDIA API call (default: {DEFAULT_EMBED_BATCH})")
    parser.add_argument("--pinecone-batch", type=int,  default=DEFAULT_PC_BATCH,
                        help=f"Vectors per Pinecone upsert batch (default: {DEFAULT_PC_BATCH})")
    parser.add_argument("--dry-run",        action="store_true",
                        help="Embed first batch only — do NOT write to Pinecone")
    parser.add_argument("--clear-index",     action="store_true",
                        help="Delete all vectors in the index before uploading")
    args = parser.parse_args()

    # ── Validate secrets ─────────────────────────────────────────────────────
    if not NV_API_KEY:
        print("✗ NV_API_KEY is not set. Add it to .env or export it as an environment variable.")
        return 1
    if not PINECONE_API_KEY and not args.dry_run:
        print("✗ PINECONE_API_KEY is not set. Add it to .env or export it as an environment variable.")
        return 1

    print()
    print("=" * 64)
    print("  EMBED + LOAD  —  NVIDIA NV-Embed-v1 → Pinecone")
    print("=" * 64)
    print(f"  Chunks dir       : {args.chunks_dir}")
    print(f"  Min tokens       : {args.min_tokens}")
    print(f"  Embed batch      : {args.embed_batch}")
    print(f"  Pinecone batch   : {args.pinecone_batch}")
    print(f"  Model            : {NV_EMBED_MODEL}")
    print(f"  Vector dim       : {VECTOR_SIZE}")
    print(f"  Pinecone index   : {PINECONE_INDEX_NAME}")
    print(f"  Pinecone host    : {PINECONE_HOST}")
    if args.dry_run:
        print("  ⚠  DRY-RUN MODE — no data will be written to Pinecone")
    print()

    # ── Step 1: Load & filter chunks ─────────────────────────────────────────
    print("─" * 64)
    print("  Step 1 — Load & filter chunks")
    print("─" * 64)
    t0 = time.monotonic()

    chunk_files = sorted(args.chunks_dir.glob("chunk_*.json"))
    if not chunk_files:
        print(f"✗ No chunk_*.json files found in {args.chunks_dir}")
        return 1
    print(f"  Total files      : {len(chunk_files):,}")

    raw_chunks: list[dict] = []
    load_errors = 0
    for fp in chunk_files:
        try:
            raw_chunks.append(json.loads(fp.read_text("utf-8")))
        except Exception as e:
            load_errors += 1
    print(f"  Loaded           : {len(raw_chunks):,} chunks  ({load_errors} errors)")

    # Filter by token count
    STRICT_MIN = max(args.min_tokens, DEFAULT_MIN_TOKENS)
    remaining, skipped_tokens = [], 0
    for c in raw_chunks:
        tok = c.get("token_count", 0)
        if tok >= STRICT_MIN:
            remaining.append(c)
        else:
            skipped_tokens += 1
    print(f"  Below {STRICT_MIN} tokens  : {skipped_tokens:,} skipped")

    # Prepare texts, filter empty / junk
    prepared: list[tuple[dict, str]] = []
    skipped_empty = 0
    for c in remaining:
        text = _prepare_text(c)
        if not text.strip() or len(text) < MIN_EMBED_CHARS:
            skipped_empty += 1
        else:
            prepared.append((c, text))

    print(f"  Empty / junk     : {skipped_empty:,} skipped")
    print(f"  To embed         : {len(prepared):,}")
    print(f"  Load time        : {time.monotonic() - t0:.1f}s")
    print()

    if not prepared:
        print("✗ No chunks survived filtering. Nothing to do.")
        return 1

    good_chunks = [p[0] for p in prepared]
    texts       = [p[1] for p in prepared]

    # ── Step 2: Connect to Pinecone ──────────────────────────────────────────
    if not args.dry_run:
        print("─" * 64)
        print("  Step 2 — Connect to Pinecone")
        print("─" * 64)
        try:
            from pinecone import Pinecone
        except ImportError:
            print("✗ pinecone not installed. Run: pip install pinecone")
            return 1

        pc    = Pinecone(api_key=PINECONE_API_KEY)
        index = pc.Index(host=PINECONE_HOST)

        if args.clear_index:
            print(f"  ⚠  Clearing all vectors from Pinecone index '{PINECONE_INDEX_NAME}'...")
            try:
                index.delete(delete_all=True)
                print("  ✓ All vectors deleted successfully.")
                time.sleep(2)  # Wait for deletion to propagate
            except Exception as e:
                print(f"  ✗ Error clearing index: {e}")
                print("  Continuing with ingestion...")

        stats = index.describe_index_stats()
        print(f"  Index            : {PINECONE_INDEX_NAME}")
        print(f"  Current vectors  : {stats.total_vector_count:,}")
        print(f"  Dimension        : {stats.dimension}")
        if stats.dimension and stats.dimension != VECTOR_SIZE:
            print(f"✗ Dimension mismatch! Index={stats.dimension}, model={VECTOR_SIZE}")
            return 1
        print()

    # ── Step 3: Embed & upsert ───────────────────────────────────────────────
    print("─" * 64)
    print("  Step 3 — Embed texts & upsert to Pinecone")
    print("─" * 64)

    total_embedded  = 0
    total_upserted  = 0
    embed_errors    = 0
    t_embed_total   = 0.0
    t_upsert_total  = 0.0

    pinecone_batch: list[dict] = []

    for batch_start in range(0, len(texts), args.embed_batch):
        batch_texts  = texts[batch_start : batch_start + args.embed_batch]
        batch_chunks = good_chunks[batch_start : batch_start + args.embed_batch]

        # ── Embed ────────────────────────────────────────────────────────────
        t_e = time.monotonic()
        try:
            vectors = _embed_batch(batch_texts, NV_API_KEY, input_type="passage")
        except Exception as exc:
            print(f"\n  ✗ Embedding error at batch {batch_start}: {exc}")
            embed_errors += len(batch_texts)
            continue
        t_embed_total += time.monotonic() - t_e
        total_embedded += len(vectors)

        if args.dry_run and batch_start == 0:
            # Dry run: just print shape and exit
            print(f"\n  ✓ DRY-RUN: embedded {len(vectors)} texts")
            print(f"  ✓ Vector shape : ({len(vectors)}, {len(vectors[0])})")
            print(f"  ✓ First 8 dims : {vectors[0][:8]}")
            print()
            print("  DRY-RUN complete — API is working correctly.")
            return 0

        # ── Build Pinecone records ────────────────────────────────────────────
        for chunk, vec in zip(batch_chunks, vectors):
            vid     = _vector_id(chunk.get("chunk_id", str(total_embedded)))
            payload = _build_payload(chunk)
            pinecone_batch.append({
                "id":     vid,
                "values": vec,
                "metadata": payload,
            })

        # ── Upsert when batch is full ─────────────────────────────────────────
        while len(pinecone_batch) >= args.pinecone_batch:
            batch_to_send = pinecone_batch[:args.pinecone_batch]
            pinecone_batch = pinecone_batch[args.pinecone_batch:]

            t_u = time.monotonic()
            index.upsert(vectors=batch_to_send)
            t_upsert_total += time.monotonic() - t_u
            total_upserted += len(batch_to_send)

        elapsed = time.monotonic() - t_e
        embed_rate   = total_embedded / max(t_embed_total,  0.001)
        upsert_rate  = total_upserted / max(t_upsert_total, 0.001)
        print(
            f"  Embedded {total_embedded:>5,}/{len(texts):,}  "
            f"upserted {total_upserted:>5,}  "
            f"[{embed_rate:.0f} emb/s  {upsert_rate:.0f} ups/s]  ",
            end="\r", flush=True,
        )

    # ── Flush remaining records ───────────────────────────────────────────────
    if pinecone_batch and not args.dry_run:
        t_u = time.monotonic()
        index.upsert(vectors=pinecone_batch)
        t_upsert_total += time.monotonic() - t_u
        total_upserted += len(pinecone_batch)
        pinecone_batch = []

    print()  # newline after progress line

    # ── Final stats ───────────────────────────────────────────────────────────
    if not args.dry_run:
        # Give Pinecone a moment to reflect the new count
        time.sleep(2)
        final_stats = index.describe_index_stats()

    print()
    print("=" * 64)
    print("  COMPLETE")
    print("=" * 64)
    print(f"  Total chunk files    : {len(chunk_files):,}")
    print(f"  Filtered out         : {skipped_tokens + skipped_empty:,}")
    print(f"    (below {STRICT_MIN} tokens)  : {skipped_tokens:,}")
    print(f"    (empty / junk)    : {skipped_empty:,}")
    print(f"  Submitted to API     : {len(prepared):,}")
    print(f"  Embedded OK          : {total_embedded:,}")
    print(f"  Embed errors         : {embed_errors:,}")
    print(f"  Upserted to Pinecone : {total_upserted:,}")
    if not args.dry_run:
        print(f"  Pinecone total now   : {final_stats.total_vector_count:,}")
    print(f"  Embed time           : {t_embed_total:.1f}s")
    if not args.dry_run:
        print(f"  Upsert time          : {t_upsert_total:.1f}s")
    print("=" * 64)
    print()

    return 0 if embed_errors == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
