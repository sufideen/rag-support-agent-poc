import pytest
from config import Config


def test_from_env_raises_when_required_vars_missing(monkeypatch):
    monkeypatch.delenv("SEARCH_ENDPOINT", raising=False)
    monkeypatch.delenv("OPENAI_ENDPOINT", raising=False)

    with pytest.raises(RuntimeError, match="SEARCH_ENDPOINT.*OPENAI_ENDPOINT"):
        Config.from_env()


def test_from_env_applies_defaults(monkeypatch):
    monkeypatch.setenv("SEARCH_ENDPOINT", "https://example.search.windows.net")
    monkeypatch.setenv("OPENAI_ENDPOINT", "https://example.openai.azure.com")
    for var in (
        "SEARCH_INDEX_NAME",
        "OPENAI_API_VERSION",
        "CHAT_DEPLOYMENT",
        "EMBEDDING_DEPLOYMENT",
        "EMBEDDING_DIMENSIONS",
        "DATA_DIR",
    ):
        monkeypatch.delenv(var, raising=False)

    config = Config.from_env()

    assert config.search_index_name == "gridpulse-support-docs"
    assert config.openai_api_version == "2024-10-21"
    assert config.chat_deployment == "gpt-5-mini"
    assert config.embedding_deployment == "text-embedding-3-small"
    assert config.embedding_dimensions == 1536


def test_from_env_overrides_defaults(monkeypatch):
    monkeypatch.setenv("SEARCH_ENDPOINT", "https://example.search.windows.net")
    monkeypatch.setenv("OPENAI_ENDPOINT", "https://example.openai.azure.com")
    monkeypatch.setenv("SEARCH_INDEX_NAME", "custom-index")
    monkeypatch.setenv("EMBEDDING_DIMENSIONS", "3072")

    config = Config.from_env()

    assert config.search_index_name == "custom-index"
    assert config.embedding_dimensions == 3072
