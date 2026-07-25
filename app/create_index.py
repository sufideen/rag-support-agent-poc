"""One-time setup script that defines and creates the Azure AI Search index
for the GridPulse Energy RAG POC.

Run once before ingest.py. Safe to re-run: it deletes and recreates the
index if it already exists, so you can iterate on the schema during
development without manually cleaning up in the Portal.

Auth: AzureCliCredential — always uses your `az login` session on this
machine specifically, rather than DefaultAzureCredential's generic fallback
chain (EnvironmentCredential/ManagedIdentityCredential can silently win
ahead of your login and authenticate as an unintended identity — hit this
in practice on vm-rag-test). No API keys anywhere, consistent with
disableLocalAuth: true on the search service itself.

Usage:
    python app/create_index.py
"""
from azure.identity import AzureCliCredential
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

from config import Config

VECTOR_PROFILE_NAME = "default-vector-profile"
VECTOR_ALGORITHM_NAME = "default-hnsw"


def build_index(config: Config) -> SearchIndex:
    fields = [
        SimpleField(name="id", type=SearchFieldDataType.String, key=True),
        SearchableField(name="content", type=SearchFieldDataType.String),
        SearchField(
            name="content_vector",
            type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
            searchable=True,
            vector_search_dimensions=config.embedding_dimensions,
            vector_search_profile_name=VECTOR_PROFILE_NAME,
        ),
        SimpleField(
            name="source",
            type=SearchFieldDataType.String,
            filterable=True,
            facetable=True,
        ),
        SimpleField(
            name="category",
            type=SearchFieldDataType.String,
            filterable=True,
            facetable=True,
        ),
        SimpleField(
            name="chunk_index",
            type=SearchFieldDataType.Int32,
            filterable=True,
        ),
    ]

    vector_search = VectorSearch(
        algorithms=[
            HnswAlgorithmConfiguration(name=VECTOR_ALGORITHM_NAME),
        ],
        profiles=[
            VectorSearchProfile(
                name=VECTOR_PROFILE_NAME,
                algorithm_configuration_name=VECTOR_ALGORITHM_NAME,
            ),
        ],
    )

    return SearchIndex(
        name=config.search_index_name,
        fields=fields,
        vector_search=vector_search,
    )


def main() -> None:
    config = Config.from_env()
    credential = AzureCliCredential()
    index_client = SearchIndexClient(endpoint=config.search_endpoint, credential=credential)

    index = build_index(config)

    print(f"Deleting index '{config.search_index_name}' if it exists...")
    index_client.delete_index(config.search_index_name)

    print(f"Creating index '{config.search_index_name}'...")
    index_client.create_index(index)

    print(f"Done. Index '{config.search_index_name}' is ready at {config.search_endpoint}")


if __name__ == "__main__":
    main()
