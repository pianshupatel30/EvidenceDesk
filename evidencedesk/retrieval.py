import hashlib
import re
from collections import Counter

import numpy as np
from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS, TfidfVectorizer

from .ingest import Chunk

STOP = set(ENGLISH_STOP_WORDS) | {"please", "tell", "does", "using"}


def tokens(text: str) -> list[str]:
    return [word for word in re.findall(r"[a-z0-9]+", text.lower()) if word not in STOP]


class Retriever:
    """Immutable corpus snapshot. A rebuilt index is swapped in by the service."""

    def __init__(self, chunks: list[Chunk], settings):
        self.chunks = chunks
        self.settings = settings
        self.fingerprint = hashlib.sha256("".join(sorted(c.id for c in chunks)).encode()).hexdigest()[:16]
        self.counts = [Counter(tokens(chunk.text)) for chunk in chunks]
        self.lengths = np.array([sum(count.values()) for count in self.counts], dtype=float)
        self.average_length = max(float(self.lengths.mean()), 1.0) if chunks else 1.0
        self.df = Counter(word for count in self.counts for word in count)
        self.encoder = None
        self.reranker = None
        self.matrix = None
        if not chunks:
            return
        texts = [chunk.text for chunk in chunks]
        if settings.vector_backend == "sentence-transformers":
            from sentence_transformers import SentenceTransformer
            self.encoder = SentenceTransformer(settings.embedding_model)
            self.matrix = self.encoder.encode(texts, normalize_embeddings=True, convert_to_numpy=True)
        else:
            self.vectorizer = TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, stop_words="english")
            try:
                self.matrix = self.vectorizer.fit_transform(texts)
            except ValueError as error:
                if "empty vocabulary" not in str(error):
                    raise
        if settings.reranker == "cross-encoder":
            from sentence_transformers import CrossEncoder
            self.reranker = CrossEncoder(settings.cross_encoder)

    def bm25(self, query: str) -> np.ndarray:
        scores = np.zeros(len(self.chunks))
        for term in set(tokens(query)):
            frequency = np.array([count.get(term, 0) for count in self.counts])
            inverse_df = np.log(1 + (len(self.chunks) - self.df[term] + 0.5) / (self.df[term] + 0.5))
            denominator = frequency + 1.5 * (0.25 + 0.75 * self.lengths / self.average_length)
            scores += inverse_df * frequency * 2.5 / denominator
        return scores

    def search(self, question: str, mode: str = "hybrid", top_k: int = 5) -> list[dict]:
        if mode not in {"keyword", "vector", "hybrid"}:
            raise ValueError("Unknown retrieval mode")
        if not self.chunks or not tokens(question):
            return []
        keyword = self.bm25(question)
        vector = np.zeros(len(self.chunks))
        if self.matrix is not None:
            if self.encoder:
                query_vector = self.encoder.encode([question], normalize_embeddings=True, convert_to_numpy=True)[0]
                vector = self.matrix @ query_vector
            else:
                vector = (self.matrix @ self.vectorizer.transform([question]).T).toarray().ravel()
        keyword_order = sorted(range(len(keyword)), key=lambda i: (-keyword[i], self.chunks[i].id))
        vector_order = sorted(range(len(vector)), key=lambda i: (-vector[i], self.chunks[i].id))
        if mode == "keyword":
            order = keyword_order
            ranking = keyword
        elif mode == "vector":
            order = vector_order
            ranking = vector
        else:
            ranking = np.zeros(len(self.chunks))
            for values, ranked in [(keyword, keyword_order), (vector, vector_order)]:
                for rank, index in enumerate(ranked[:20], 1):
                    if values[index] > 0:
                        ranking[index] += 1 / (60 + rank)
            order = sorted(range(len(ranking)), key=lambda i: (-ranking[i], self.chunks[i].id))
        query_terms = set(tokens(question))
        results = []
        for index in order[:20]:
            if ranking[index] <= 0:
                continue
            coverage = len(query_terms & self.counts[index].keys()) / max(len(query_terms), 1)
            results.append({**self.chunks[index].to_dict(), "score": float(ranking[index]),
                            "similarity": float(vector[index]), "coverage": coverage})
        # Baselines retain their own ranking. Reranking applies only to hybrid.
        if mode == "hybrid" and results:
            if self.reranker:
                reranked = self.reranker.predict([(question, hit["text"]) for hit in results])
                for hit, score in zip(results, reranked):
                    hit["rerank_score"] = float(score)
            else:
                for hit in results:
                    hit["rerank_score"] = hit["score"] + 0.02 * hit["coverage"]
            results.sort(key=lambda hit: (-hit["rerank_score"], hit["id"]))
        return results[:top_k]

    def sufficient(self, hits: list[dict]) -> bool:
        return bool(hits and hits[0]["similarity"] >= self.settings.min_similarity
                    and hits[0]["coverage"] >= self.settings.min_coverage)
