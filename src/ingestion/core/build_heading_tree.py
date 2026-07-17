from __future__ import annotations

import json
import re
from pathlib import Path

from config import PROCESSED_DIR
from utils import is_table_line, is_list_line, heading_level


def build_heading_tree(markdown: str) -> dict:
    lines = markdown.splitlines()
    root = {'level': 1, 'heading': 'root', 'children': [], 'content': []}
    path = [root]

    current_block: list[str] = []
    current_block_type: str = 'paragraph'

    def flush_block():
        if not current_block:
            return
        text = '\n'.join(current_block).strip()
        if not text:
            return
        path[-1]['content'].append({
            'type': current_block_type,
            'text': text,
        })
        current_block.clear()

    i = 0
    while i < len(lines):
        line = lines[i]
        level = heading_level(line)

        if level is not None and 1 <= level <= 4:
            flush_block()

            while len(path) > 1 and path[-1]['level'] >= level:
                path.pop()
            while len(path) > 1 and level < path[-1]['level']:
                path.pop()

            heading_text = re.sub(r'^#+\s+', '', line).strip()
            node = {
                'level': level,
                'heading': heading_text,
                'children': [],
                'content': [],
            }
            path[-1]['children'].append(node)
            path.append(node)
            current_block_type = 'paragraph'
            i += 1
            continue

        if is_table_line(line):
            flush_block()
            table_lines = [line]
            i += 1
            while i < len(lines) and is_table_line(lines[i]):
                table_lines.append(lines[i])
                i += 1
            path[-1]['content'].append({
                'type': 'table',
                'text': '\n'.join(table_lines),
            })
            current_block_type = 'paragraph'
            continue

        if is_list_line(line):
            list_lines = [line]
            i += 1
            while i < len(lines) and is_list_line(lines[i]):
                list_lines.append(lines[i])
                i += 1
            path[-1]['content'].append({
                'type': 'list',
                'text': '\n'.join(list_lines),
            })
            current_block_type = 'paragraph'
            continue

        current_block.append(line)
        current_block_type = 'paragraph'
        i += 1

    flush_block()
    return root


def flatten_tree(node: dict, parent_chain: list[str] | None = None) -> list[dict]:
    sections = []
    chain = list(parent_chain) if parent_chain else []

    if node['heading'] != 'root':
        chain.append(node['heading'])

    if node['content']:
        sections.append({
            'heading_chain': list(chain),
            'content': node['content'],
        })

    for child in node['children']:
        sections.extend(flatten_tree(child, chain))
    return sections


def main() -> None:
    json_files = sorted(PROCESSED_DIR.glob('*.json'))
    if not json_files:
        print('No processed documents found. Run classify_pages.py first.')
        return

    print(f'Building heading trees for {len(json_files)} documents ...')

    for fp in json_files:
        doc = json.loads(fp.read_text(encoding='utf-8'))
        tree = build_heading_tree(doc['clean_content'])
        sections = flatten_tree(tree)
        doc['heading_tree'] = tree
        doc['sections'] = sections
        doc['section_count'] = len(sections)
        fp.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding='utf-8')

    print('  Done.')


if __name__ == '__main__':
    main()
