from pathlib import Path

from ingestion.preprocess_documents import PreprocessorConfig, preprocess_markdown_text


def test_preprocess_markdown_removes_navigation_and_footer_noise(tmp_path: Path) -> None:
    sample = """---
url: https://example.com/page
depth: 3
crawled_at: 2026-07-13T00:00:00Z
---

| [Home](https://example.com) | [About](https://example.com/about) |
| --- | --- |
| [Contact](https://example.com/contact) | [Syllabus](https://example.com/syllabus) |

# Welcome

This is a paragraph with extra  spaces.

- First bullet
- Second bullet

1. First numbered item
2. Second numbered item

| Name | Value |
| --- | --- |
| A | 1 |

Copyright © Example. All rights reserved.
Hosted and maintained by NIC.

[![](https://example.com/logo.jpg)](https://example.com)

[Back to Top](#top)

"""

    config = PreprocessorConfig(input_dir=tmp_path / "pages", output_dir=tmp_path / "processed")
    cleaned = preprocess_markdown_text(sample, config=config)

    assert "# Welcome" in cleaned
    assert "This is a paragraph" in cleaned
    assert "Copyright" not in cleaned
    assert "Hosted" not in cleaned
    assert "Back to Top" not in cleaned
    assert "Home" not in cleaned
    assert "About" not in cleaned
    assert "logo" not in cleaned
    assert "| Name | Value |" in cleaned
