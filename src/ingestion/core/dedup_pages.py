from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from config import PROCESSED_DIR
from utils import sha256_of_text


def main() -> None:
    json_files = sorted(PROCESSED_DIR.glob('*.json'))
    if not json_files:
        print('No processed documents found. Run clean_pages.py first.')
        return

    print(f'Deduplicating {len(json_files)} documents ...')

    docs: list[dict] = []
    for fp in json_files:
        try:
            docs.append(json.loads(fp.read_text(encoding='utf-8')))
        except Exception as e:
            print(f'  WARN: skipping {fp.name}: {e}')

    # Pass 1: URL dedup — keep lowest depth, then newest
    by_url: dict[str, list[dict]] = defaultdict(list)
    for doc in docs:
        by_url[doc['url']].append(doc)

    url_deduped: list[dict] = []
    url_removed = 0
    for url, group in by_url.items():
        if len(group) == 1:
            url_deduped.append(group[0])
        else:
            group.sort(key=lambda d: (d['depth'], d.get('crawled_at', '')), reverse=True)
            url_deduped.append(group[-1])
            url_removed += len(group) - 1

    print(f'  After URL dedup: {len(url_deduped)} documents ({url_removed} removed)')

    # Pass 2: content hash dedup
    by_hash: dict[str, list[dict]] = defaultdict(list)
    for doc in url_deduped:
        h = sha256_of_text(doc['clean_content'])
        by_hash[h].append(doc)

    final: list[dict] = []
    hash_removed = 0
    for h, group in by_hash.items():
        if len(group) == 1:
            final.append(group[0])
        else:
            group.sort(key=lambda d: len(d['url']))
            final.append(group[0])
            hash_removed += len(group) - 1

    print(f'  After content hash dedup: {len(final)} documents ({hash_removed} removed)')
    print(f'  Total removed: {url_removed + hash_removed}')

    # Overwrite processed files with deduplicated set
    kept_ids = {d['doc_id'] for d in final}
    for fp in json_files:
        doc_id = fp.stem
        if doc_id not in kept_ids:
            fp.unlink()
            continue
    for doc in final:
        out_path = PROCESSED_DIR / f'{doc["doc_id"]}.json'
        out_path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding='utf-8')

    print(f'  Kept: {len(final)} files | Removed: {url_removed + hash_removed}')


if __name__ == '__main__':
    main()
