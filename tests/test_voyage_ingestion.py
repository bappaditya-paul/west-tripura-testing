from unimplement.voyage_ingestion import prepare_text


def test_prepare_text_rejects_heading_only_chunks() -> None:
    chunk = {
        "heading_chain": ["Tenders", "Find Services"],
        "title": "More Menu",
        "content": "## Find Services",
        "token_count": 3,
    }

    assert prepare_text(chunk) == ""


def test_prepare_text_keeps_meaningful_content() -> None:
    chunk = {
        "heading_chain": ["Tenders", "Find Services"],
        "title": "More Menu",
        "content": "The college publishes tenders and service notices for applicants.",
        "token_count": 12,
    }

    text = prepare_text(chunk)
    assert "Tenders > Find Services" in text
    assert "The college publishes tenders" in text
