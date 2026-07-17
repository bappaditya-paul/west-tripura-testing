from __future__ import annotations

import hashlib
import json
from pathlib import Path

from config import CHUNKS_DIR
from utils import contains_bengali


def main() -> None:
    chunks_path = CHUNKS_DIR / 'chunks.jsonl'
    if not chunks_path.exists():
        print('No chunks found. Run chunk_pages.py first.')
        return

    out_path = CHUNKS_DIR / 'chunks.jsonl'
    lines = chunks_path.read_text(encoding='utf-8').splitlines()
    print(f'Enriching metadata for {len(lines)} chunks ...')

    doc_chunk_counters: dict[str, int] = {}
    enriched: list[str] = []

    for line in lines:
        chunk = json.loads(line)
        doc_id = chunk['doc_id']

        doc_chunk_counters[doc_id] = doc_chunk_counters.get(doc_id, 0) + 1
        chunk_index = doc_chunk_counters[doc_id] - 1

        chunk_id = hashlib.md5(
            f"{chunk['url']}::{chunk_index}".encode()
        ).hexdigest()

        heading_chain = chunk.get('heading_chain', [])
        heading_depth = len(heading_chain)
        section = heading_chain[-1] if heading_chain else ''
        sub_section = heading_chain[-2] if len(heading_chain) >= 2 else ''

        language = 'bn' if contains_bengali(chunk.get('text', '')) else 'en'

        enriched_chunk = {
            'chunk_id': chunk_id,
            'document_id': doc_id,
            'title': chunk.get('title', ''),
            'url': chunk.get('url', ''),
            'domain': chunk.get('domain', ''),
            'category': chunk.get('category', 'general'),
            'section': section,
            'sub_section': sub_section,
            'heading_chain': heading_chain,
            'heading_depth': heading_depth,
            'language': language,
            'has_table': chunk.get('has_table', False),
            'has_list': chunk.get('has_list', False),
            'token_count': chunk.get('token_count', 0),
            'chunk_index': chunk_index,
            'total_chunks': doc_chunk_counters[doc_id],
            'text': chunk['text'],
            'source_file': chunk.get('source_file', ''),
            'crawled_at': chunk.get('crawled_at', ''),
            'depth': chunk.get('depth', 0),
        }
        enriched.append(json.dumps(enriched_chunk, ensure_ascii=False))

    out_path.write_text('\n'.join(enriched) + '\n', encoding='utf-8')
    print(f'  Wrote {len(enriched)} enriched chunks')

    lang_counts: dict[str, int] = {}
    table_count = 0
    for line in enriched:
        c = json.loads(line)
        lang = c['language']
        lang_counts[lang] = lang_counts.get(lang, 0) + 1
        if c['has_table']:
            table_count += 1

    print(f'  Language distribution: {lang_counts}')
    print(f'  Chunks with tables: {table_count}')


if __name__ == '__main__':
    main()
