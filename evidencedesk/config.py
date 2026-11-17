import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


@dataclass(frozen=True)
class Settings:
    documents: Path = ROOT / "documents"
    database: Path = ROOT / "data" / "requests.sqlite3"
    provider: str = os.getenv("ED_PROVIDER", "extractive")
    vector_backend: str = os.getenv("ED_VECTOR_BACKEND", "tfidf")
    reranker: str = os.getenv("ED_RERANKER", "coverage")
    min_similarity: float = float(os.getenv("ED_MIN_SIMILARITY", "0.16"))
    min_coverage: float = float(os.getenv("ED_MIN_COVERAGE", "0.45"))
    embedding_model: str = os.getenv("ED_EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
    cross_encoder: str = os.getenv("ED_CROSS_ENCODER", "cross-encoder/ms-marco-MiniLM-L-6-v2")
    ollama_url: str = os.getenv("ED_OLLAMA_URL", "http://localhost:11434")
    ollama_model: str = os.getenv("ED_OLLAMA_MODEL", "qwen2.5:3b")
    api_base: str = os.getenv("ED_API_BASE", "https://api.openai.com/v1")
    api_key: str = os.getenv("ED_API_KEY", "")
    model: str = os.getenv("ED_MODEL", "")
    input_price: str = os.getenv("ED_INPUT_PRICE", "")
    output_price: str = os.getenv("ED_OUTPUT_PRICE", "")

    def __post_init__(self):
        if self.provider not in {"extractive", "ollama", "openai-compatible"}:
            raise ValueError("ED_PROVIDER must be extractive, ollama, or openai-compatible")
        if self.vector_backend not in {"tfidf", "sentence-transformers"}:
            raise ValueError("ED_VECTOR_BACKEND must be tfidf or sentence-transformers")
        if self.reranker not in {"coverage", "cross-encoder"}:
            raise ValueError("ED_RERANKER must be coverage or cross-encoder")
        if not 0 <= self.min_similarity <= 1 or not 0 <= self.min_coverage <= 1:
            raise ValueError("Retrieval thresholds must be between zero and one")
        for price in (self.input_price, self.output_price):
            if price and (not float(price) >= 0 or not float(price) < float("inf")):
                raise ValueError("Token prices must be finite and nonnegative")
