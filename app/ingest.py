"""Chunks data/*.md, embeds each chunk via Azure OpenAI, and upserts into Azure AI Search.

Requires the index to already exist — run `python app/create_index.py` once
first.

Usage:
    python app/ingest.py

Auth is Entra ID only (disableLocalAuth=true on both services) via
DefaultAzureCredential — run `az login` first.
"""
import glob
import os
import re
import sys

from azure.core.exceptions import ResourceNotFoundError
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient
from config import Config
from openai import AzureOpenAI

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


def check_index_exists(config: Config, credential) -> None:
    index_client = SearchIndexClient(config.search_endpoint, credential)
    try:
        index_client.get_index(config.search_index_name)
    except ResourceNotFoundError:
        raise RuntimeError(
            f"Index '{config.search_index_name}' doesn't exist. "
            "Run `python app/create_index.py` first."
        ) from None


def embed_all(openai_client: AzureOpenAI, config: Config, texts: list[str]) -> list[list[float]]:
    response = openai_client.embeddings.create(model=config.embedding_deployment, input=texts)
    return [item.embedding for item in response.data]


def main() -> int:
    config = Config.from_env()
    credential = DefaultAzureCredential()
    check_index_exists(config, credential)

    search_client = SearchClient(config.search_endpoint, config.search_index_name, credential)
    openai_client = AzureOpenAI(
        azure_endpoint=config.openai_endpoint,
        azure_ad_token_provider=get_bearer_token_provider(credential, COGNITIVE_SERVICES_SCOPE),
        api_version=config.openai_api_version,
    )

    documents = []
    for path in sorted(glob.glob(os.path.join(config.data_dir, "*.md"))):
        source = os.path.basename(path)
        category = os.path.splitext(source)[0]
        with open(path, encoding="utf-8-sig") as f:
            text = f.read()
        for i, chunk in enumerate(chunk_markdown(text)):
            documents.append(
                {
                    "id": f"{category}-{i}",
                    "content": chunk,
                    "source": source,
                    "category": category,
                    "chunk_index": i,
                }
            )

    if not documents:
        print(f"No markdown files found in {config.data_dir}", file=sys.stderr)
        return 1

    vectors = embed_all(openai_client, config, [d["content"] for d in documents])
    for doc, vector in zip(documents, vectors):
        doc["content_vector"] = vector

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
