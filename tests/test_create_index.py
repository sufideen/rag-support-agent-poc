from azure.search.documents.indexes.models import SearchFieldDataType
from config import Config
from create_index import VECTOR_ALGORITHM_NAME, VECTOR_PROFILE_NAME, build_index


def _config(embedding_dimensions=1536):
    return Config(
        search_endpoint="https://example.search.windows.net",
        search_index_name="gridpulse-support-docs",
        openai_endpoint="https://example.openai.azure.com",
        openai_api_version="2024-10-21",
        chat_deployment="gpt-5-mini",
        embedding_deployment="text-embedding-3-small",
        embedding_dimensions=embedding_dimensions,
        data_dir="/tmp/does-not-matter",
    )


def test_build_index_uses_configured_name_and_dimensions():
    index = build_index(_config(embedding_dimensions=3072))

    assert index.name == "gridpulse-support-docs"
    vector_field = next(f for f in index.fields if f.name == "content_vector")
    assert vector_field.vector_search_dimensions == 3072


def test_build_index_declares_expected_fields():
    index = build_index(_config())

    fields_by_name = {f.name: f for f in index.fields}
    assert set(fields_by_name) == {"id", "content", "content_vector", "source", "category", "chunk_index"}
    assert fields_by_name["id"].key is True
    assert fields_by_name["chunk_index"].type == SearchFieldDataType.Int32
    assert fields_by_name["source"].filterable is True
    assert fields_by_name["category"].facetable is True


def test_build_index_vector_search_wiring():
    index = build_index(_config())

    profile_names = {p.name for p in index.vector_search.profiles}
    algorithm_names = {a.name for a in index.vector_search.algorithms}
    assert VECTOR_PROFILE_NAME in profile_names
    assert VECTOR_ALGORITHM_NAME in algorithm_names
