from __future__ import annotations

import json
import re
from pathlib import Path

from config import PAGES_DIR, PROCESSED_DIR
from utils import parse_frontmatter, url_to_domain, url_to_slug


NOISE_PATTERNS: list[re.Pattern] = [
    # Skip-to-content / accessibility skip links
    re.compile(r'\[.*?Skip to main content.*?\]\(.*?\)', re.IGNORECASE),
    re.compile(r'\[.*?সরাসরি মূল কন্টেন্টে.*?\]\(.*?\)'),
    # Search bars: "Search Search" or "অনুসন্ধান অনুসন্ধান"
    re.compile(r'^\s*\*?\s*(Search|অনুসন্ধান)\s+(Search|অনুসন্ধান)\s*$', re.MULTILINE),
    re.compile(r'^\s*\*?\s*\[.*?Search.*?\]', re.MULTILINE),
    # Site map links
    re.compile(r'\[Site Map\].*?Sitemap.*?\]', re.IGNORECASE),
    re.compile(r'\[সাইট ম্যাপ\].*?সাইটম্যাপ.*?\]'),
    # Social media link containers
    re.compile(r'\[Social Media Links\].*?\]', re.IGNORECASE),
    re.compile(r'\[সামাজিক মিডিয়া লিঙ্ক\].*?\]'),
    # Accessibility: Color Contrast blocks
    re.compile(
        r'(?:Color Contrast|Text Size|Other Controls|Accessibility Tools)'
        r'[\s\S]*?(?=\n\S|\Z)',
        re.IGNORECASE,
    ),
    # Accessibility individual lines
    re.compile(r'^[\*\- ]*(High Contrast|Normal Contrast|Highlight Links|Invert|Saturation)'
               r'.*$', re.MULTILINE | re.IGNORECASE),
    re.compile(r'^[\*\- ]*(Font Size Increase|Normal Font|Font Size Decrease|Text Spacing|Line Height)'
               r'.*$', re.MULTILINE | re.IGNORECASE),
    re.compile(r'^[\*\- ]*(Big Cursor|Hide Image|Hide images|Show images)'
               r'.*$', re.MULTILINE | re.IGNORECASE),
    re.compile(r'^[\*\- ]*(ফন্ট সাইজ|নর্মাল ফন্ট|ফন্ট সাইজ বৃদ্ধি|ফন্ট সাইজ হ্রাস)'
               r'.*$', re.MULTILINE),
    # Back to top image links
    re.compile(r'\[.*!\[.*\]\(.*\)\]\(.*back2top.*\)'),
    re.compile(r'!\[.*back2top.*\]\(.*\)'),
    # Separator images (bar1.gif etc)
    re.compile(r'!\[.*bar\d?\.gif.*\]\(.*\)'),
    # Logo image rows (usually in tables)
    re.compile(r'^\|?\s*!\[.*logo.*\]\(.*\)\s*\|?\s*$', re.MULTILINE | re.IGNORECASE),
    # Lines that are just image markdown with no text
    re.compile(r'^\s*!\[.*\]\(.*\)\s*$', re.MULTILINE),
    # Empty table rows (just pipes and dashes)
    re.compile(r'^\|[\|\s\-:]+\|$', re.MULTILINE),
    # Lines that are pure links (navigation rows) - like "| [Home](...) | [About](...) | [Contact](...) |"
    re.compile(r'^\|[\s\|\[\]\(\)\w\d\s\.\/\-\_]+$', re.MULTILINE),
    # Image links in square brackets followed by nothing relevant
    re.compile(r'\[!\[.*\]\(.*\)\]\(.*\)'),
    # Footer copyright
    re.compile(
        r'(?:Copyright|©|Disclaimer|Terms\s*&\s*Conditions|Privacy\s*Policy)'
        r'.*$', re.IGNORECASE | re.MULTILINE
    ),
    # Server Error / 404 pages
    re.compile(r'^#\s*Server\s*Error$', re.MULTILINE | re.IGNORECASE),
    re.compile(r'^##\s*404\s*-', re.MULTILINE | re.IGNORECASE),
]


def is_noise_file(body: str) -> bool:
    if re.search(r'^#\s*Server\s*Error', body, re.MULTILINE | re.IGNORECASE):
        return True
    if re.search(r'^##\s*404\s*-', body, re.MULTILINE | re.IGNORECASE):
        return True
    return False


def clean_body(body: str) -> str:
    for pattern in NOISE_PATTERNS:
        body = pattern.sub('', body)
    lines = body.splitlines()
    cleaned: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped == '':
            if cleaned and cleaned[-1] != '':
                cleaned.append('')
            continue
        if stripped in ('|', '||', '-', '---', '****', '**', ''):
            continue
        if stripped.startswith('|') and stripped.endswith('|'):
            inner = stripped[1:-1].strip()
            if all(part.strip() in ('', '-') for part in inner.split('|')):
                continue
        cleaned.append(stripped)
    result = re.sub(r'\n{3,}', '\n\n', '\n'.join(cleaned))
    return result.strip()


def main() -> None:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    md_files = sorted(PAGES_DIR.glob('*.md'))
    print(f'Cleaning {len(md_files)} markdown files ...')

    cleaned_count = 0
    skipped_count = 0

    for md_path in md_files:
        raw = md_path.read_text(encoding='utf-8')
        frontmatter, body = parse_frontmatter(raw)
        url = frontmatter.get('url', '')
        if not url:
            skipped_count += 1
            continue
        if is_noise_file(body):
            skipped_count += 1
            continue
        clean = clean_body(body)
        if len(clean) < 100:
            skipped_count += 1
            continue
        doc = {
            'doc_id': url_to_slug(url),
            'title': md_path.stem.split('__')[0].replace('_', ' ').title(),
            'url': url,
            'domain': url_to_domain(url),
            'depth': int(frontmatter.get('depth', 0)),
            'score': int(frontmatter.get('score', 0)),
            'crawled_at': frontmatter.get('crawled_at', ''),
            'original_file': str(md_path.relative_to(md_path.parent.parent.parent)),
            'clean_content': clean,
            'raw_char_count': len(body),
            'clean_char_count': len(clean),
        }
        out_path = PROCESSED_DIR / f'{doc["doc_id"]}.json'
        out_path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding='utf-8')
        cleaned_count += 1

    print(f'  Cleaned: {cleaned_count}')
    print(f'  Skipped: {skipped_count}')
    print(f'  Output: {PROCESSED_DIR.resolve()}')


if __name__ == '__main__':
    main()
