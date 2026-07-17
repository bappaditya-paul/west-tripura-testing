from __future__ import annotations

import json
from pathlib import Path

from config import PROCESSED_DIR, CHUNKS_DIR, CHUNK_TOKEN_SIZE, CHUNK_OVERLAP
from utils import estimate_tokens


def content_token_count(content_block: dict) -> int:
    return estimate_tokens(content_block.get('text', ''))


def chunk_document(doc: dict) -> list[dict]:
    sections = doc.get('sections', [])
    if not sections:
        sections = [{
            'heading_chain': [doc.get('title', '')],
            'content': [{'type': 'paragraph', 'text': doc.get('clean_content', '')}],
        }]

    chunks: list[dict] = []
    heading_chain = doc.get('heading_chain', [])

    for section in sections:
        chain = heading_chain + section.get('heading_chain', [])
        content_blocks = section.get('content', [])

        current_text = ''
        current_tokens = 0
        current_blocks: list[dict] = []

        def emit_chunk():
            nonlocal current_text, current_tokens, current_blocks
            if not current_text.strip():
                return
            prefix = ' > '.join(chain) + '\n\n' if chain else ''
            full_text = prefix + current_text.strip()
            chunks.append({
                'heading_chain': list(chain),
                'text': full_text.strip(),
                'token_count': estimate_tokens(full_text.strip()),
                'has_table': any(b.get('type') == 'table' for b in current_blocks),
                'has_list': any(b.get('type') == 'list' for b in current_blocks),
                'content_blocks': current_blocks,
            })
            current_blocks = []

        for block in content_blocks:
            block_text = block.get('text', '')
            block_tokens = content_token_count(block)

            if block['type'] == 'table':
                if current_blocks:
                    emit_chunk()
                if block_tokens > CHUNK_TOKEN_SIZE:
                    rows = block_text.splitlines()
                    header = rows[0] if len(rows) > 1 else ''
                    sep = rows[1] if len(rows) > 1 else ''
                    data_rows = rows[2:] if len(rows) > 2 else rows
                    current_table_chunk = header + '\n' + sep + '\n' if header and sep else ''
                    current_table_tokens = estimate_tokens(current_table_chunk) if current_table_chunk else 0

                    for row in data_rows:
                        row_tokens = estimate_tokens(row)
                        if current_table_tokens + row_tokens > CHUNK_TOKEN_SIZE and current_table_chunk:
                            prefix = ' > '.join(chain) + '\n\n' if chain else ''
                            chunks.append({
                                'heading_chain': list(chain),
                                'text': (prefix + current_table_chunk).strip(),
                                'token_count': estimate_tokens((prefix + current_table_chunk).strip()),
                                'has_table': True,
                                'has_list': False,
                                'content_blocks': [{'type': 'table', 'text': current_table_chunk}],
                            })
                            current_table_chunk = ''
                            current_table_tokens = 0
                        current_table_chunk += row + '\n'
                        current_table_tokens += row_tokens

                    if current_table_chunk.strip():
                        prefix = ' > '.join(chain) + '\n\n' if chain else ''
                        chunks.append({
                            'heading_chain': list(chain),
                            'text': (prefix + current_table_chunk).strip(),
                            'token_count': estimate_tokens((prefix + current_table_chunk).strip()),
                            'has_table': True,
                            'has_list': False,
                            'content_blocks': [{'type': 'table', 'text': current_table_chunk}],
                        })
                else:
                    prefix = ' > '.join(chain) + '\n\n' if chain else ''
                    full_text = prefix + block_text
                    chunks.append({
                        'heading_chain': list(chain),
                        'text': full_text.strip(),
                        'token_count': estimate_tokens(full_text.strip()),
                        'has_table': True,
                        'has_list': False,
                        'content_blocks': [block],
                    })
                continue

            if block['type'] == 'list':
                if current_blocks:
                    emit_chunk()
                prefix = ' > '.join(chain) + '\n\n' if chain else ''
                full_text = prefix + block_text
                chunks.append({
                    'heading_chain': list(chain),
                    'text': full_text.strip(),
                    'token_count': estimate_tokens(full_text.strip()),
                    'has_table': False,
                    'has_list': True,
                    'content_blocks': [block],
                })
                continue

            if current_tokens + block_tokens > CHUNK_TOKEN_SIZE and current_blocks:
                emit_chunk()
                current_text = ''
                current_tokens = 0

            if current_text:
                current_text += '\n\n'
            current_text += block_text
            current_tokens += block_tokens
            current_blocks.append(block)

        if current_blocks:
            emit_chunk()

    return chunks


def main() -> None:
    json_files = sorted(PROCESSED_DIR.glob('*.json'))
    if not json_files:
        print('No processed documents found. Run build_heading_tree.py first.')
        return

    CHUNKS_DIR.mkdir(parents=True, exist_ok=True)
    chunks_path = CHUNKS_DIR / 'chunks.jsonl'

    print(f'Chunking {len(json_files)} documents ...')
    print(f'  Token size: {CHUNK_TOKEN_SIZE}, Overlap: {CHUNK_OVERLAP}')

    total_chunks = 0
    with chunks_path.open('w', encoding='utf-8') as out:
        for fp in json_files:
            doc = json.loads(fp.read_text(encoding='utf-8'))
            chunks = chunk_document(doc)
            for chunk in chunks:
                record = {
                    'doc_id': doc['doc_id'],
                    'url': doc['url'],
                    'domain': doc['domain'],
                    'category': doc.get('category', 'general'),
                    'title': doc.get('title', ''),
                    'depth': doc.get('depth', 0),
                    'crawled_at': doc.get('crawled_at', ''),
                    'source_file': doc.get('original_file', ''),
                    'heading_chain': chunk['heading_chain'],
                    'text': chunk['text'],
                    'token_count': chunk['token_count'],
                    'has_table': chunk['has_table'],
                    'has_list': chunk['has_list'],
                    'chunk_index': total_chunks,
                }
                out.write(json.dumps(record, ensure_ascii=False) + '\n')
                total_chunks += 1

    print(f'  Total chunks: {total_chunks}')
    print(f'  Output: {chunks_path.resolve()}')


if __name__ == '__main__':
    main()
