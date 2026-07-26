"""Minimal HTTP front end for the RAG pipeline, wrapping the same
retrieve/generate_answer/is_flagged logic as the query.py CLI behind a
FastAPI app so it can run as a long-lived service instead of a one-shot
command.

Like the CLI, this still needs to run from inside the VNet (private
endpoints only) — see docs/architecture.md.

Usage:
    uvicorn app.api:app --host 0.0.0.0 --port 8000
"""
from functools import lru_cache

from azure.ai.contentsafety import ContentSafetyClient
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from azure.search.documents import SearchClient
from config import Config
from fastapi import Depends, FastAPI
from fastapi.responses import HTMLResponse
from openai import AzureOpenAI
from pydantic import BaseModel
from query import COGNITIVE_SERVICES_SCOPE, REFUSAL_MESSAGE, generate_answer, is_flagged, retrieve

app = FastAPI(title="GridPulse RAG Support Agent")


@lru_cache
def get_config() -> Config:
    return Config.from_env()


@lru_cache
def get_credential() -> DefaultAzureCredential:
    return DefaultAzureCredential()


@lru_cache
def get_search_client() -> SearchClient:
    config = get_config()
    return SearchClient(config.search_endpoint, config.search_index_name, get_credential())


@lru_cache
def get_openai_client() -> AzureOpenAI:
    config = get_config()
    return AzureOpenAI(
        azure_endpoint=config.openai_endpoint,
        azure_ad_token_provider=get_bearer_token_provider(get_credential(), COGNITIVE_SERVICES_SCOPE),
        api_version=config.openai_api_version,
    )


@lru_cache
def get_content_safety_client() -> ContentSafetyClient:
    config = get_config()
    return ContentSafetyClient(config.content_safety_endpoint, get_credential())


class QueryRequest(BaseModel):
    question: str
    top_k: int = 3


class QueryResponse(BaseModel):
    answer: str


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.post("/query", response_model=QueryResponse)
def query(
    request: QueryRequest,
    config: Config = Depends(get_config),
    search_client: SearchClient = Depends(get_search_client),
    openai_client: AzureOpenAI = Depends(get_openai_client),
    content_safety_client: ContentSafetyClient = Depends(get_content_safety_client),
) -> QueryResponse:
    if is_flagged(content_safety_client, request.question):
        return QueryResponse(answer=REFUSAL_MESSAGE)

    chunks = retrieve(search_client, openai_client, config, request.question, request.top_k)
    if not chunks:
        return QueryResponse(answer="No relevant support articles found for that question.")

    answer = generate_answer(openai_client, config, request.question, chunks)
    if is_flagged(content_safety_client, answer):
        return QueryResponse(answer=REFUSAL_MESSAGE)

    return QueryResponse(answer=answer)


INDEX_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>GridPulse Energy Support</title>
<style>
  body { font-family: system-ui, sans-serif; max-width: 40rem; margin: 3rem auto; padding: 0 1rem; }
  textarea { width: 100%; box-sizing: border-box; }
  #answer { white-space: pre-wrap; border-left: 3px solid #ccc; padding-left: 1rem; margin-top: 1rem; }
</style>
</head>
<body>
<h1>GridPulse Energy Support</h1>
<form id="ask-form">
  <textarea id="question" rows="2" placeholder="How do I report an outage?"></textarea>
  <button type="submit">Ask</button>
</form>
<div id="answer"></div>
<script>
document.getElementById("ask-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const question = document.getElementById("question").value;
  const answerEl = document.getElementById("answer");
  answerEl.textContent = "Thinking...";
  const response = await fetch("/query", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question }),
  });
  const data = await response.json();
  answerEl.textContent = response.ok ? data.answer : `Error: ${JSON.stringify(data)}`;
});
</script>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return INDEX_HTML
