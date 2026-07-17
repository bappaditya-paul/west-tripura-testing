from __future__ import annotations

from ingestion.markdown_parser import parse_markdown_document


def test_parse_markdown_document_builds_heading_tree() -> None:
    markdown = """# Root Heading

This is a paragraph under the root heading.

## Child Heading

- first item
- second item

### Grandchild Heading

| a | b |
| --- | --- |
| 1 | 2 |

> quoted text

```python
print('hello')
```
"""

    parsed = parse_markdown_document(markdown, metadata={"source_path": "example.md"})

    assert parsed.document_id == "example_md"
    assert parsed.tree.type == "document"

    root_heading = parsed.tree.children[0]
    assert root_heading.type == "heading"
    assert root_heading.title == "Root Heading"

    child_heading = next(child for child in root_heading.children if child.type == "heading" and child.title == "Child Heading")
    assert child_heading.type == "heading"
    assert child_heading.title == "Child Heading"

    grandchild_heading = next(child for child in child_heading.children if child.type == "heading" and child.title == "Grandchild Heading")
    assert grandchild_heading.type == "heading"
    assert grandchild_heading.title == "Grandchild Heading"
    assert any(node.type == "paragraph" for node in root_heading.children)
