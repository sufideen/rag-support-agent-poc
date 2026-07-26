from unittest.mock import MagicMock

from config import Config
from query import generate_answer, retrieve


def _config():
    return Config(
        search_endpoint="https://example.search.windows.net",
        search_index_name="gridpulse-support-docs",
        openai_endpoint="https://example.openai.azure.com",
        openai_api_version="2024-10-21",
        chat_deployment="gpt-5-mini",
        embedding_deployment="text-embedding-3-small",
        embedding_dimensions=1536,
        data_dir="/tmp/does-not-matter",
    )


def test_retrieve_embeds_question_and_searches_with_the_resulting_vector():
    config = _config()
    openai_client = MagicMock()
    openai_client.embeddings.create.return_value.data = [MagicMock(embedding=[0.1, 0.2, 0.3])]
    search_client = MagicMock()
    expected_chunks = [{"content": "some content", "source": "billing-payment.md"}]
    search_client.search.return_value = iter(expected_chunks)

    chunks = retrieve(search_client, openai_client, config, "How do I pay my bill?", top_k=3)

    assert chunks == expected_chunks
    openai_client.embeddings.create.assert_called_once_with(
        model=config.embedding_deployment, input=["How do I pay my bill?"]
    )
    _, kwargs = search_client.search.call_args
    assert kwargs["select"] == ["content", "source"]
    assert kwargs["vector_queries"][0].k_nearest_neighbors == 3
    assert kwargs["vector_queries"][0].vector == [0.1, 0.2, 0.3]


def test_generate_answer_grounds_the_prompt_in_retrieved_chunks():
    config = _config()
    openai_client = MagicMock()
    openai_client.chat.completions.create.return_value.choices = [
        MagicMock(message=MagicMock(content="You can pay online."))
    ]
    chunks = [{"source": "billing-payment.md", "content": "Pay via the customer portal."}]

    answer = generate_answer(openai_client, config, "How do I pay my bill?", chunks)

    assert answer == "You can pay online."
    _, kwargs = openai_client.chat.completions.create.call_args
    assert kwargs["model"] == config.chat_deployment
    user_message = kwargs["messages"][1]["content"]
    assert "[billing-payment.md]" in user_message
    assert "Pay via the customer portal." in user_message
    assert "How do I pay my bill?" in user_message
