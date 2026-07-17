# West Tripura NIC Website Crawler

A production-ready crawler for [westtripura.nic.in](https://westtripura.nic.in/) that:

- 🕸️ **Deep crawls** the entire site (BFS, up to depth 5, max 2000 pages)
- 📄 **Extracts clean Markdown** from every page
- 💾 **Saves crash-recovery checkpoints** (resume with `--resume` after any interruption)
- 🧩 **Chunks Markdown** into overlapping passages ready for vector DB ingestion
- 📊 **Produces a JSONL manifest** and chunk file for easy downstream processing

---

## Project Structure

```
west-tripura-chabtot/
├── crawler.py          ← Main crawler (run this first)
├── chunker.py          ← Chunk markdown pages for vector DB
├── inspect_output.py   ← Inspect stats / sample output
├── requirements.txt
└── output/             ← Created automatically
    ├── pages/          ← One .md file per crawled page
    ├── manifest.jsonl  ← Metadata for every crawled page
    ├── chunks.jsonl    ← Chunked passages (after running chunker.py)
    ├── checkpoint.json ← Crash-recovery state
    └── crawl.log       ← Full crawl log
```

---

## Quick Start

### 1. Install dependencies

```bash
pip install crawl4ai
crawl4ai-setup          # installs Playwright + Chromium
```

### 2. Run the crawler

```bash
python crawler.py
```

The crawler streams results as they arrive and saves each page to `output/pages/`.

### 3. Resume after interruption

```bash
python crawler.py --resume
```

### 4. Chunk for vector DB

```bash
python chunker.py                          # default 600-char chunks, 80-char overlap
python chunker.py --chunk-size 800 --overlap 100   # custom sizes
```

### 5. Inspect output

```bash
python inspect_output.py
```

---

## Output Format

### Pages (`output/pages/*.md`)

Each page is saved as Markdown with a YAML frontmatter header:

```markdown
---
url: https://westtripura.nic.in/about/
depth: 1
score: 0
crawled_at: 2024-07-12T00:00:00Z
---

# About West Tripura

...page content...
```

### Manifest (`output/manifest.jsonl`)

One JSON line per crawled page:
```json
{"url": "https://...", "file": "pages/...", "depth": 1, "char_count": 4200, "crawled_at": "..."}
```

### Chunks (`output/chunks.jsonl`)

One JSON line per chunk, ready to embed:
```json
{
  "chunk_id": "abc123",
  "url": "https://...",
  "depth": 1,
  "chunk_index": 0,
  "total_chunks": 3,
  "text": "... passage text ...",
  "char_count": 612,
  "crawled_at": "..."
}
```

---

## Vector DB Ingestion

Load chunks directly:

```python
import json

chunks = [json.loads(line) for line in open("output/chunks.jsonl")]

# Example: embed with sentence-transformers
from sentence_transformers import SentenceTransformer
model = SentenceTransformer("all-MiniLM-L6-v2")
embeddings = model.encode([c["text"] for c in chunks], batch_size=32)

# Example: upsert to Chroma
import chromadb
client = chromadb.Client()
col = client.create_collection("westtripura")
col.add(
    ids=[c["chunk_id"] for c in chunks],
    documents=[c["text"] for c in chunks],
    metadatas=[{"url": c["url"], "depth": c["depth"]} for c in chunks],
    embeddings=embeddings.tolist()
)
```

---

## Configuration

Edit the constants at the top of `crawler.py`:

| Variable | Default | Description |
|---|---|---|
| `MAX_DEPTH` | `5` | Link-levels deep from the start URL |
| `MAX_PAGES` | `2000` | Hard cap on total pages crawled |
| `CONCURRENCY` | `3` | Parallel browser contexts |
| `DELAY_BETWEEN_REQUESTS` | `1.5s` | Politeness delay between batches |

---

## Crash Recovery

The crawler saves a `checkpoint.json` after **every page**. If it crashes or you press `Ctrl+C`, resume with:

```bash
python crawler.py --resume
```

It will skip already-crawled URLs and continue from the pending queue.

---

## Tips for Government Sites

- **Be polite**: Keep `CONCURRENCY ≤ 3` and `DELAY_BETWEEN_REQUESTS ≥ 1.0` for govt servers
- **Check robots.txt**: `https://westtripura.nic.in/robots.txt`
- **PDF pages**: Some govt pages link to PDFs — Crawl4AI skips them automatically
- **Duplicate content**: The chunker de-duplicates nearly-empty pages (< 50 chars)
