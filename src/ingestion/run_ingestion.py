"""
run_ingestion.py
================
West Tripura RAG — Master Ingestion Orchestrator

Runs the complete ingestion pipeline end-to-end:

  Phase 9  → Embed chunks           (BAAI/bge-m3, local model)
  Phase 10 → Load to Qdrant         (Dense + Sparse vectors)

Prerequisites (already complete):
  Phase 1-8 output lives in processed_chunks/*.json

Usage:
    python run_ingestion.py                      # full pipeline
    python run_ingestion.py --embed-only         # stop after embedding
    python run_ingestion.py --load-only          # skip embedding, just load
    python run_ingestion.py --force-embed        # re-embed even if done
    python run_ingestion.py --force-recreate     # recreate Qdrant collection
    python run_ingestion.py --batch-size 4       # smaller GPU/CPU batches
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent.parent))

from src.ingestion.core.config import (
    PROCESSED_CHUNKS_DIR,
    COLLECTION_NAME,
    QDRANT_HOST,
    QDRANT_PORT,
    EMBED_BATCH_SIZE,
    BATCH_SIZE,
    LOCAL_MODEL_PATH,
    MODEL_NAME,
    VECTOR_SIZE,
)
from src.ingestion.core.embedder     import embed_chunks
from src.ingestion.core.qdrant_loader import load_to_qdrant


# ─────────────────────────────────────────────────────────────────────────────
# Banner
# ─────────────────────────────────────────────────────────────────────────────

def _print_banner() -> None:
    chunk_count = len(list(PROCESSED_CHUNKS_DIR.glob("chunk_*.json")))
    model_source = str(LOCAL_MODEL_PATH) if LOCAL_MODEL_PATH and LOCAL_MODEL_PATH.exists() \
                   else f"HuggingFace ({MODEL_NAME})"
    print("""
╔══════════════════════════════════════════════════════════════╗
║       WEST TRIPURA RAG — Ingestion Pipeline                  ║
║       NIC District Chatbot Vector Database Builder           ║
╠══════════════════════════════════════════════════════════════╣""")
    print(f"║  Chunks to process : {chunk_count:<39,}║")
    print(f"║  Embedding model   : BAAI/bge-m3 (dim={VECTOR_SIZE})          ║")
    print(f"║  Vector DB         : Qdrant @ {QDRANT_HOST}:{QDRANT_PORT}              ║")
    print(f"║  Collection        : {COLLECTION_NAME:<39}║")
    print("""╚══════════════════════════════════════════════════════════════╝
""")


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="run_ingestion",
        description="West Tripura RAG — Full Ingestion Pipeline (Phases 9-10)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run_ingestion.py                        # standard full run
  python run_ingestion.py --embed-only           # embed only (no Qdrant load)
  python run_ingestion.py --load-only            # Qdrant load only
  python run_ingestion.py --force-embed          # re-embed all chunks
  python run_ingestion.py --force-recreate       # delete + reload Qdrant
  python run_ingestion.py --batch-size 4         # slow machine / low RAM
""",
    )
    p.add_argument(
        "--embed-only", action="store_true",
        help="Run only the embedding phase (Phase 9)",
    )
    p.add_argument(
        "--load-only", action="store_true",
        help="Run only the Qdrant loading phase (Phase 10), skip embedding",
    )
    p.add_argument(
        "--force-embed", action="store_true",
        help="Re-embed all chunks even if embedded_chunks.jsonl already exists",
    )
    p.add_argument(
        "--force-recreate", action="store_true",
        help="Delete and recreate the Qdrant collection before loading",
    )
    p.add_argument(
        "--batch-size", type=int, default=EMBED_BATCH_SIZE,
        help=f"Embedding batch size (default: {EMBED_BATCH_SIZE})",
    )
    p.add_argument(
        "--qdrant-batch", type=int, default=BATCH_SIZE,
        help=f"Qdrant upsert batch size (default: {BATCH_SIZE})",
    )
    p.add_argument(
        "--skip-indexes", action="store_true",
        help="Skip creating Qdrant payload indexes (faster for re-loads)",
    )
    return p


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main() -> int:
    args = _build_parser().parse_args()

    _print_banner()
    t_overall = time.monotonic()
    summaries: dict[str, dict] = {}

    # ── Phase 9: Embedding ────────────────────────────────────────────────────
    if not args.load_only:
        print("\n" + "─" * 62)
        print("  Phase 9 — Embedding  (BAAI/bge-m3)")
        print("─" * 62)
        t0 = time.monotonic()
        result = embed_chunks(
            chunks_dir=PROCESSED_CHUNKS_DIR,
            batch_size=args.batch_size,
            force=args.force_embed,
        )
        result["phase_elapsed_s"] = round(time.monotonic() - t0, 1)
        summaries["embedding"] = result

        if "error" in result:
            print(f"\n✗ Embedding failed: {result['error']}")
            return 1

        print(f"\n  ✓ Phase 9 complete — {result['embedded']:,} vectors "
              f"in {result['phase_elapsed_s']}s")

    if args.embed_only:
        print("\n  --embed-only flag set, stopping here.")
        _print_summary(summaries, time.monotonic() - t_overall)
        return 0

    # ── Phase 10: Qdrant Load ─────────────────────────────────────────────────
    print("\n" + "─" * 62)
    print("  Phase 10 — Qdrant Load  (Dense + BM25 Sparse)")
    print("─" * 62)
    t0 = time.monotonic()
    result = load_to_qdrant(
        chunks_dir=PROCESSED_CHUNKS_DIR,
        batch_size=args.qdrant_batch,
        force_recreate=args.force_recreate,
        skip_indexes=args.skip_indexes,
    )
    result["phase_elapsed_s"] = round(time.monotonic() - t0, 1)
    summaries["qdrant"] = result

    if "error" in result:
        print(f"\n✗ Qdrant load failed: {result['error']}")
        return 1

    print(f"\n  ✓ Phase 10 complete — {result['loaded']:,} points loaded "
          f"in {result['phase_elapsed_s']}s")

    # ── Final summary ─────────────────────────────────────────────────────────
    _print_summary(summaries, time.monotonic() - t_overall)
    return 0


def _print_summary(summaries: dict, total_elapsed: float) -> None:
    print("\n" + "╔" + "═" * 60 + "╗")
    print("║" + "  PIPELINE COMPLETE".center(60) + "║")
    print("╠" + "═" * 60 + "╣")

    if "embedding" in summaries:
        e = summaries["embedding"]
        skipped = " (cached)" if e.get("skipped") else ""
        print(f"║  Embedded vectors : {e.get('embedded', 0):<38,}║"
              .replace("(cached)", skipped))
    if "qdrant" in summaries:
        q = summaries["qdrant"]
        print(f"║  Qdrant points    : {q.get('loaded', 0):<39,}║")
        print(f"║  Collection total : {q.get('total', 0):<39,}║")

    mins = total_elapsed / 60
    print(f"║  Total time       : {total_elapsed:.1f}s  ({mins:.1f}m)".ljust(61) + "║")
    print(f"║  Dashboard →  http://localhost:{QDRANT_PORT}/dashboard".ljust(61) + "║")
    print("╚" + "═" * 60 + "╝\n")


if __name__ == "__main__":
    sys.exit(main())
