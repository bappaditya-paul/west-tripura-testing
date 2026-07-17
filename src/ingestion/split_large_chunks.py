"""
split_large_chunks.py
=====================
Step 2 of Chunk Quality Improvement Plan.
Splits chunks that are > 500 tokens into smaller, overlapping chunks (~400 tokens with ~50 overlap).
Handles English sentences (. ) and Bengali sentences (। ) properly.
"""

import os
import sys
import json
import re
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent.parent))

CLEAN_CHUNKS_DIR = _HERE.parent.parent / "clean_chunks"

TARGET_TOKENS = 400
MAX_TOKENS = 500
OVERLAP_TOKENS = 50

# Regex to split text into sentences (handles English .!? and Bengali ।)
SENTENCE_SPLIT_RE = re.compile(r'(?<=[.!?।])\s+|\n\n+')

def get_content(chunk: dict) -> str:
    return (chunk.get("content") or chunk.get("text") or "").strip()

def estimate_tokens(text: str) -> int:
    """
    Rough token count estimator.
    Generally, 1 word is ~1.3 tokens for English/Bengali mixed text.
    """
    words = text.split()
    return int(len(words) * 1.3)

def split_text_into_overlapping_chunks(text: str, target: int, overlap: int) -> list[str]:
    """Splits text into chunks of target size with overlap, keeping sentence integrity."""
    sentences = [s.strip() for s in SENTENCE_SPLIT_RE.split(text) if s.strip()]
    if not sentences:
        return [text]
        
    chunks = []
    current_sentences = []
    current_tokens = 0
    
    for sentence in sentences:
        s_tokens = estimate_tokens(sentence)
        
        # If a single sentence is extremely long, split by words
        if s_tokens > target:
            words = sentence.split()
            word_batch = []
            word_tokens = 0
            for word in words:
                word_batch.append(word)
                word_tokens += 1.3
                if word_tokens >= target:
                    current_sentences.append(" ".join(word_batch))
                    word_batch = []
                    word_tokens = 0
            if word_batch:
                current_sentences.append(" ".join(word_batch))
            continue
            
        if current_tokens + s_tokens > target:
            # Emit current chunk
            chunks.append(" ".join(current_sentences))
            
            # Form next chunk starting with some overlapping sentences from the end
            overlap_sentences = []
            overlap_tokens = 0
            for s in reversed(current_sentences):
                ot = estimate_tokens(s)
                if overlap_tokens + ot <= overlap:
                    overlap_sentences.insert(0, s)
                    overlap_tokens += ot
                else:
                    break
            
            current_sentences = overlap_sentences + [sentence]
            current_tokens = overlap_tokens + s_tokens
        else:
            current_sentences.append(sentence)
            current_tokens += s_tokens
            
    if current_sentences:
        chunks.append(" ".join(current_sentences))
        
    return chunks

def main():
    print("=" * 60)
    print("  STEP 2: SPLIT LARGE CHUNKS")
    print("=" * 60)
    
    chunk_files = sorted(CLEAN_CHUNKS_DIR.glob("chunk_*.json"))
    if not chunk_files:
        print(f"✗ No chunk files found in {CLEAN_CHUNKS_DIR}. Did you run clean_chunks.py?")
        return 1
        
    all_chunks = []
    for fp in chunk_files:
        try:
            all_chunks.append(json.loads(fp.read_text("utf-8")))
        except Exception as e:
            print(f"Error loading {fp.name}: {e}")
            
    print(f"Loaded {len(all_chunks)} clean chunks.")
    
    final_chunks = []
    splits_count = 0
    
    for chunk in all_chunks:
        content = get_content(chunk)
        tokens = chunk.get("token_count", 0)
        
        # If the chunk is small enough, keep it as-is
        if tokens <= MAX_TOKENS:
            final_chunks.append(chunk)
            continue
            
        # We need to split this chunk!
        splits_count += 1
        sub_texts = split_text_into_overlapping_chunks(content, TARGET_TOKENS, OVERLAP_TOKENS)
        
        orig_id = chunk.get("chunk_id", "chunk")
        total_parts = len(sub_texts)
        
        for idx, sub_text in enumerate(sub_texts):
            split_chunk = chunk.copy()
            split_chunk["chunk_id"] = f"{orig_id}_part_{idx}"
            split_chunk["content"] = sub_text
            split_chunk["text"] = sub_text
            
            # Recalculate token count
            new_tokens = estimate_tokens(sub_text)
            split_chunk["token_count"] = new_tokens
            split_chunk["character_count"] = len(sub_text)
            
            # Add split tracking metadata
            split_chunk["split_part"] = idx
            split_chunk["split_total"] = total_parts
            
            # Adjust title slightly to indicate part
            orig_title = chunk.get("title", "")
            split_chunk["title"] = f"{orig_title} (Part {idx + 1}/{total_parts})"
            
            final_chunks.append(split_chunk)
            
    # Clear out the directory and rewrite all files
    for f in CLEAN_CHUNKS_DIR.glob("chunk_*.json"):
        f.unlink()
        
    for i, chunk in enumerate(final_chunks):
        out_fp = CLEAN_CHUNKS_DIR / f"chunk_{i:06d}.json"
        out_fp.write_text(json.dumps(chunk, indent=2, ensure_ascii=False), "utf-8")
        
    print("\n" + "─" * 60)
    print("  SPLITTING REPORT")
    print("─" * 60)
    print(f"  Clean chunks loaded : {len(all_chunks):>5,}")
    print(f"  Chunks split        : {splits_count:>5,}")
    print(f"  ─────────────────────────")
    print(f"  Total final chunks  : {len(final_chunks):>5,}")
    print("=" * 60)
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
