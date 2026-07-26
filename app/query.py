"""Answers a customer support question by retrieving relevant chunks from
Azure AI Search and generating a grounded answer with Azure OpenAI, with
Azure AI Content Safety moderating both the question and the answer.

Usage:
    python app/query.py "How do I reset my password?"

Auth is Entra ID only (disableLocalAuth=true on all three services) via
DefaultAzureCredential — run `az login` first.
"""
import argparse
import sys

from azure.ai.contentsafety import ContentSafetyClient
from azure.ai.contentsafety.models import AnalyzeTextOptions
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from azure.search.documents import SearchClient
from azure.search.documents.models import VectorizedQuery
from config import Config
from openai import AzureOpenAI

COGNITIVE_SERVICES_SCOPE = "https://cognitiveservices.azure.com/.default"

# Azure Content Safety reports severity per category on a 0/2/4/6 scale.
# 4 ("medium") is Azure's own recommended default block threshold.
SEVERITY_BLOCK_THRESHOLD = 4

SYSTEM_PROMPT = (
    "You are a customer support assistant for GridPulse Energy, a utility company. "
    "Answer only using the provided context from the support knowledge base. "
    "If the answer isn't in the context, say you don't have that information "
    "and suggest the customer contact support directly. Keep answers concise."
)

REFUSAL_MESSAGE = (
    "I can't help with that request. Please contact GridPulse Energy support directly."
)


def is_flagged(content_safety_client: ContentSafetyClient, text: str) -> bool:
    result = content_safety_client.analyze_text(AnalyzeTextOptions(text=text))
    return any(category.severity >= SEVERITY_BLOCK_THRESHOLD for category in result.categories_analysis)


def retrieve(search_client: SearchClient, openai_client: AzureOpenAI, config: Config, question: str, top_k: int):
    vector = openai_client.embeddings.create(model=config.embedding_deployment, input=[question]).data[0].embedding
    results = search_client.search(
        search_text=None,
        vector_queries=[
            VectorizedQuery(vector=vector, k_nearest_neighbors=top_k, fields="content_vector")
        ],
        select=["content", "source"],
    )
    return list(results)


def generate_answer(openai_client: AzureOpenAI, config: Config, question: str, chunks: list) -> str:
    context = "\n\n".join(f"[{c['source']}]\n{c['content']}" for c in chunks)
    response = openai_client.chat.completions.create(
        model=config.chat_deployment,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {question}"},
        ],
    )
    return response.choices[0].message.content


def main() -> int:
    parser = argparse.ArgumentParser(description="Query the GridPulse RAG support agent")
    parser.add_argument("question", help="Customer question")
    parser.add_argument("--top-k", type=int, default=3, help="Number of chunks to retrieve")
    args = parser.parse_args()

    config = Config.from_env()
    credential = DefaultAzureCredential()

    search_client = SearchClient(config.search_endpoint, config.search_index_name, credential)
    openai_client = AzureOpenAI(
        azure_endpoint=config.openai_endpoint,
        azure_ad_token_provider=get_bearer_token_provider(credential, COGNITIVE_SERVICES_SCOPE),
        api_version=config.openai_api_version,
    )
    content_safety_client = ContentSafetyClient(config.content_safety_endpoint, credential)

    if is_flagged(content_safety_client, args.question):
        print(REFUSAL_MESSAGE)
        return 0

    chunks = retrieve(search_client, openai_client, config, args.question, args.top_k)
    if not chunks:
        print("No relevant support articles found for that question.")
        return 0

    answer = generate_answer(openai_client, config, args.question, chunks)
    if is_flagged(content_safety_client, answer):
        print(REFUSAL_MESSAGE)
        return 0

    print(answer)
    return 0


if __name__ == "__main__":
    sys.exit(main())
