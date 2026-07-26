from unittest.mock import MagicMock

import api
from api import app, get_config, get_content_safety_client, get_openai_client, get_search_client
from config import Config
from fastapi.testclient import TestClient


def _config():
    return Config(
        search_endpoint="https://example.search.windows.net",
        search_index_name="gridpulse-support-docs",
        openai_endpoint="https://example.openai.azure.com",
        openai_api_version="2024-10-21",
        chat_deployment="gpt-5-mini",
        embedding_deployment="text-embedding-3-small",
        embedding_dimensions=1536,
        content_safety_endpoint="https://example.cognitiveservices.azure.com",
        data_dir="/tmp/does-not-matter",
    )


def _category(severity):
    return MagicMock(severity=severity)


def _client(*, question_severity=0, answer_severity=0, chunks=None, answer_text="You can pay online."):
    search_client = MagicMock()
    search_client.search.return_value = iter(
        chunks if chunks is not None else [{"source": "billing-payment.md", "content": "Pay via the portal."}]
    )

    openai_client = MagicMock()
    openai_client.embeddings.create.return_value.data = [MagicMock(embedding=[0.1, 0.2, 0.3])]
    openai_client.chat.completions.create.return_value.choices = [MagicMock(message=MagicMock(content=answer_text))]

    content_safety_client = MagicMock()
    severities = iter([question_severity, answer_severity])
    content_safety_client.analyze_text.side_effect = lambda *a, **k: MagicMock(
        categories_analysis=[_category(next(severities))]
    )

    app.dependency_overrides[get_config] = _config
    app.dependency_overrides[get_search_client] = lambda: search_client
    app.dependency_overrides[get_openai_client] = lambda: openai_client
    app.dependency_overrides[get_content_safety_client] = lambda: content_safety_client
    return TestClient(app)


def teardown_function():
    app.dependency_overrides.clear()


def test_healthz():
    client = _client()
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_index_serves_html():
    client = _client()
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


def test_query_returns_grounded_answer():
    client = _client()
    response = client.post("/query", json={"question": "How do I pay my bill?"})
    assert response.status_code == 200
    assert response.json() == {"answer": "You can pay online."}


def test_query_refuses_when_question_is_flagged():
    client = _client(question_severity=6)
    response = client.post("/query", json={"question": "something unsafe"})
    assert response.status_code == 200
    assert response.json() == {"answer": api.REFUSAL_MESSAGE}


def test_query_refuses_when_answer_is_flagged():
    client = _client(answer_severity=6)
    response = client.post("/query", json={"question": "How do I pay my bill?"})
    assert response.status_code == 200
    assert response.json() == {"answer": api.REFUSAL_MESSAGE}


def test_query_reports_no_articles_found_when_search_returns_nothing():
    client = _client(chunks=[])
    response = client.post("/query", json={"question": "How do I pay my bill?"})
    assert response.status_code == 200
    assert response.json() == {"answer": "No relevant support articles found for that question."}
