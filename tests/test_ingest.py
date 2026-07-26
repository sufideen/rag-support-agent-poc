from unittest.mock import MagicMock

import pytest
from azure.core.exceptions import ResourceNotFoundError
from config import Config
from ingest import check_index_exists, chunk_markdown


def test_chunk_markdown_splits_on_headings():
    text = "## First\ncontent one\n## Second\ncontent two"
    chunks = chunk_markdown(text)
    assert chunks == ["## First\ncontent one", "## Second\ncontent two"]


def test_chunk_markdown_no_headings_returns_single_chunk():
    text = "just some text with no heading"
    assert chunk_markdown(text) == [text]


def test_chunk_markdown_empty_input_returns_no_chunks():
    assert chunk_markdown("") == []
    assert chunk_markdown("   \n  ") == []


def test_chunk_markdown_hard_wraps_oversized_section():
    text = "## Heading\n" + ("x" * 25)
    chunks = chunk_markdown(text, max_chars=10)
    assert len(chunks) > 1
    assert "".join(chunks) == text


def _config(**overrides):
    defaults = dict(
        search_endpoint="https://example.search.windows.net",
        search_index_name="test-index",
        openai_endpoint="https://example.openai.azure.com",
        openai_api_version="2024-10-21",
        chat_deployment="gpt-5-mini",
        embedding_deployment="text-embedding-3-small",
        embedding_dimensions=1536,
        content_safety_endpoint="https://example.cognitiveservices.azure.com",
        data_dir="/tmp/does-not-matter",
    )
    defaults.update(overrides)
    return Config(**defaults)


def test_check_index_exists_passes_when_index_found(monkeypatch):
    index_client = MagicMock()
    monkeypatch.setattr("ingest.SearchIndexClient", lambda *a, **k: index_client)

    check_index_exists(_config(), credential=MagicMock())

    index_client.get_index.assert_called_once_with("test-index")


def test_check_index_exists_raises_clear_error_when_missing(monkeypatch):
    index_client = MagicMock()
    index_client.get_index.side_effect = ResourceNotFoundError("not found")
    monkeypatch.setattr("ingest.SearchIndexClient", lambda *a, **k: index_client)

    with pytest.raises(RuntimeError, match="create_index.py"):
        check_index_exists(_config(), credential=MagicMock())
