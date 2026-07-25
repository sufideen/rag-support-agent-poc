"""Chunks data/*.md, embeds each chunk via Azure OpenAI, and upserts into Azure AI Search.

Usage:
    python app/ingest.py

Auth is Entra ID only (disableLocalAuth=true on both services) via
DefaultAzureCredential — run `az login` first.
"""
import glob
import os
import re
import sys

from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    HnswAlgorithmConfiguration,
    SearchableField,
    SearchField,
    SearchFieldDataType,
    SearchIndex,
    SimpleField,
    VectorSearch,
    VectorSearchProfile,
)
from openai import AzureOpenAI

from config import Config

VECTOR_PROFILE_NAME = "default-profile"
VECTOR_ALGORITHM_NAME = "default-hnsw"
COGNITIVE_SERVICES_SCOPE = "https://cognitiveservices.azure.com/.default"


def chunk_markdown(text: str, max_chars: int = 1200) -> list[str]:
    """Splits on '## ' section headings, then hard-wraps any oversized section."""
    sections = re.split(r"(?=^## )", text, flags=re.MULTILINE)
    chunks = []
    for section in sections:
        section = section.strip()
        if not section:
            continue
        for i in range(0, len(section), max_chars):
            chunks.append(section[i : i + max_chars])
    return chunks


def ensure_index(index_client: SearchIndexClient, config: Config) -> None:
    existing = {index.name for index in index_client.list_indexes()}
    if config.search_index_name in existing:
        return

    fields = [
        SimpleField(name="id", type=SearchFieldDataType.String, key=True),
        SearchableField(name="content", type=SearchFieldDataType.String),
        SimpleField(name="source", type=SearchFieldDataType.String, filterable=True),
        SearchField(
            name="contentVector",
            type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
            searchable=True,
            vector_search_dimensions=config.embedding_dimensions,
            vector_search_profile_name=VECTOR_PROFILE_NAME,
        ),
    ]
    vector_search = VectorSearch(
        algorithms=[HnswAlgorithmConfiguration(name=VECTOR_ALGORITHM_NAME)],
        profiles=[
            VectorSearchProfile(
                name=VECTOR_PROFILE_NAME,
                algorithm_configuration_name=VECTOR_ALGORITHM_NAME,
            )
        ],
    )
    index_client.create_index(
        SearchIndex(name=config.search_index_name, fields=fields, vector_search=vector_search)
    )
    print(f"Created index '{config.search_index_name}'")


def embed_all(openai_client: AzureOpenAI, config: Config, texts: list[str]) -> list[list[float]]:
    response = openai_client.embeddings.create(model=config.embedding_deployment, input=texts)
    return [item.embedding for item in response.data]


def main() -> int:
    config = Config.from_env()
    credential = DefaultAzureCredential()

    index_client = SearchIndexClient(config.search_endpoint, credential)
    ensure_index(index_client, config)

    search_client = SearchClient(config.search_endpoint, config.search_index_name, credential)
    openai_client = AzureOpenAI(
        azure_endpoint=config.openai_endpoint,
        azure_ad_token_provider=get_bearer_token_provider(credential, COGNITIVE_SERVICES_SCOPE),
        api_version=config.openai_api_version,
    )

    documents = []
    for path in sorted(glob.glob(os.path.join(config.data_dir, "*.md"))):
        source = os.path.basename(path)
        with open(path, encoding="utf-8") as f:
            text = f.read()
        for i, chunk in enumerate(chunk_markdown(text)):
            documents.append({"id": f"{source}-{i}", "content": chunk, "source": source})

    if not documents:
        print(f"No markdown files found in {config.data_dir}", file=sys.stderr)
        return 1

    vectors = embed_all(openai_client, config, [d["content"] for d in documents])
    for doc, vector in zip(documents, vectors):
        doc["contentVector"] = vector

    results = search_client.upload_documents(documents)
    failed = [r for r in results if not r.succeeded]
    if failed:
        print(f"{len(failed)} of {len(documents)} documents failed to upload:", file=sys.stderr)
        for r in failed:
            print(f"  {r.key}: {r.error_message}", file=sys.stderr)
        return 1

    sources = {d["source"] for d in documents}
    print(f"Ingested {len(documents)} chunks from {len(sources)} files into '{config.search_index_name}'")
    return 0


if __name__ == "__main__":
    sys.exit(main())
