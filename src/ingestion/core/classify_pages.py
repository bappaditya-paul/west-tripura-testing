from __future__ import annotations

import json
from pathlib import Path

from config import PROCESSED_DIR


import re


URL_PATTERNS: list[tuple[str, re.Pattern]] = [
    ('admission', re.compile(r'admission|admit|merit.?list|spot.?round|lateral', re.IGNORECASE)),
    ('tender', re.compile(r'tender|quotation', re.IGNORECASE)),
    ('syllabus', re.compile(r'syllabus|syllabi|curriculum', re.IGNORECASE)),
    ('scholarship', re.compile(r'scholarship', re.IGNORECASE)),
    ('form', re.compile(r'form|application', re.IGNORECASE)),
    ('gallery', re.compile(r'gallery', re.IGNORECASE)),
    ('newsletter', re.compile(r'newsletter', re.IGNORECASE)),
    ('academic_calendar', re.compile(r'academic.?calend|calender|semester', re.IGNORECASE)),
    ('committee', re.compile(r'committee|anti.?ragging|council', re.IGNORECASE)),
    ('report', re.compile(r'eoa|aicte|approval', re.IGNORECASE)),
    ('contact', re.compile(r'contact.?us|contactus', re.IGNORECASE)),
    ('service', re.compile(r'service|public.?utility', re.IGNORECASE)),
    ('event', re.compile(r'event', re.IGNORECASE)),
    ('about', re.compile(r'about|history|location|principal', re.IGNORECASE)),
    ('faculty_staff', re.compile(r'faculty|staff|office.?staff', re.IGNORECASE)),
    ('department', re.compile(r'department|cst|itcs|etce|mlt|ft', re.IGNORECASE)),
    ('notice', re.compile(r'notice|notification|circular|past.?notice', re.IGNORECASE)),
    ('fee', re.compile(r'fee.?structure|fee_', re.IGNORECASE)),
]

CONTENT_PATTERNS: list[tuple[str, re.Pattern]] = [
    ('admission', re.compile(r'admission|merit list|spot round|lateral entry|ভর্তি', re.IGNORECASE)),
    ('tender', re.compile(r'tender|quotation|দরপত্র', re.IGNORECASE)),
    ('syllabus', re.compile(r'syllabus|curriculum|semester|পাঠ্যক্রম', re.IGNORECASE)),
    ('scholarship', re.compile(r'scholarship|বৃত্তি', re.IGNORECASE)),
    ('newsletter', re.compile(r'newsletter', re.IGNORECASE)),
    ('report', re.compile(r'eoa|aicte|approval process', re.IGNORECASE)),
    ('committee', re.compile(r'committee|anti.?ragging|council|কমিটি', re.IGNORECASE)),
    ('fee', re.compile(r'fee structure|fees?|টিউশন ফি', re.IGNORECASE)),
    ('form', re.compile(r'form|registration|ফর্ম', re.IGNORECASE)),
    ('contact', re.compile(r'contact|যোগাযোগ', re.IGNORECASE)),
    ('service', re.compile(r'service|public.*utility|পরিষেবা', re.IGNORECASE)),
    ('gallery', re.compile(r'gallery|ছবি', re.IGNORECASE)),
    ('event', re.compile(r'event|কার্যক্রম', re.IGNORECASE)),
    ('about', re.compile(r'about|history|location|পরিচিতি', re.IGNORECASE)),
    ('faculty_staff', re.compile(r'faculty|staff|principal|teacher|শিক্ষক', re.IGNORECASE)),
    ('department', re.compile(r'department|cst|itcs|etce|mlt|ft|বিভাগ', re.IGNORECASE)),
    ('notice', re.compile(r'notice|notification|circular|announcement|বিজ্ঞপ্তি|নোটিশ', re.IGNORECASE)),
]

DEPARTMENT_CODE_MAP: dict[str, str] = {
    'cst': 'department', 'itcs': 'department', 'etce': 'department',
    'mlt': 'department', 'ft': 'department',
    'it': 'department', 'computer': 'department', 'science': 'department',
    'fashion': 'department', 'medical': 'department', 'electronic': 'department',
    'telecommunication': 'department',
}


def classify_document(doc: dict) -> str:
    url = doc.get('url', '')
    title = doc.get('title', '')
    content = doc.get('clean_content', '')[:2000]

    # Pass 1: URL-based classification (most reliable)
    for category, pattern in URL_PATTERNS:
        if pattern.search(url):
            return category

    # Pass 2: Title-based
    for category, pattern in URL_PATTERNS:
        if pattern.search(title):
            return category

    # Pass 3: Content-based fallback
    for category, pattern in CONTENT_PATTERNS:
        if pattern.search(content):
            return category

    return 'general'


def main() -> None:
    json_files = sorted(PROCESSED_DIR.glob('*.json'))
    if not json_files:
        print('No processed documents found. Run dedup_pages.py first.')
        return

    print(f'Classifying {len(json_files)} documents ...')

    category_counts: dict[str, int] = {}
    for fp in json_files:
        doc = json.loads(fp.read_text(encoding='utf-8'))
        category = classify_document(doc)
        doc['category'] = category
        fp.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding='utf-8')
        category_counts[category] = category_counts.get(category, 0) + 1

    print('  Category distribution:')
    for cat, count in sorted(category_counts.items(), key=lambda x: -x[1]):
        print(f'    {cat}: {count}')
    print(f'  Total: {sum(category_counts.values())}')


if __name__ == '__main__':
    main()
