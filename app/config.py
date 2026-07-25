import os
from dataclasses import dataclass

_DEFAULT_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")


@dataclass
class Config:
    search_endpoint: str
    search_index_name: str
    openai_endpoint: str
    openai_api_version: str
    chat_deployment: str
    embedding_deployment: str
    embedding_dimensions: int
    data_dir: str

    @classmethod
    def from_env(cls) -> "Config":
        required = ("SEARCH_ENDPOINT", "OPENAI_ENDPOINT")
        missing = [name for name in required if not os.environ.get(name)]
        if missing:
            raise RuntimeError(
                f"Missing required environment variables: {', '.join(missing)}. "
                "See .env.example."
            )

        return cls(
            search_endpoint=os.environ["SEARCH_ENDPOINT"],
            search_index_name=os.environ.get("SEARCH_INDEX_NAME", "gridpulse-support-kb"),
            openai_endpoint=os.environ["OPENAI_ENDPOINT"],
            openai_api_version=os.environ.get("OPENAI_API_VERSION", "2024-10-21"),
            chat_deployment=os.environ.get("CHAT_DEPLOYMENT", "gpt-5-mini"),
            embedding_deployment=os.environ.get("EMBEDDING_DEPLOYMENT", "text-embedding-3-small"),
            embedding_dimensions=int(os.environ.get("EMBEDDING_DIMENSIONS", "1536")),
            data_dir=os.environ.get("DATA_DIR", _DEFAULT_DATA_DIR),
        )
