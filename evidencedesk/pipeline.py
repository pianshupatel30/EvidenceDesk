import base64
import binascii
import hashlib
import os
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .ingest import MAX_BYTES, chunk_document, load_documents
from .providers import GenerationError, estimate_cost, generate
from .retrieval import Retriever
from .telemetry import Telemetry


class Service:
    def __init__(self, settings):
        self.settings = settings
        self.lock = threading.RLock()
        settings.documents.mkdir(parents=True, exist_ok=True)
        self.telemetry = Telemetry(settings.database)
        chunks, self.warnings = load_documents(settings.documents)
        self.index = Retriever(chunks, settings)

    def info(self):
        with self.lock:
            return {"provider": self.settings.provider, "vector_backend": self.settings.vector_backend,
                    "reranker": self.settings.reranker, "index_version": self.index.fingerprint,
                    "chunks": len(self.index.chunks), "documents": sorted({c.source for c in self.index.chunks}),
                    "warnings": self.warnings}

    def upload(self, filename: str, encoded: str):

        try:
            content = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error) as error:
            raise ValueError("Invalid file encoding") from error
        suffix = Path(filename).suffix.lower()
        digest = hashlib.sha256(content).hexdigest()[:16]
        name = f"user_{digest}{suffix}"
        incoming = chunk_document(name, content)
        with self.lock:
            if any(chunk.source == name for chunk in self.index.chunks):
                return {"source": name, "deduplicated": True, **self.info()}
            if len({chunk.source for chunk in self.index.chunks}) >= 100:
                raise ValueError("This local demo supports up to 100 documents")
            # Build the candidate first. A failure leaves the active index intact.
            candidate = Retriever(self.index.chunks + incoming, self.settings)
            temporary = self.settings.documents / (name + ".tmp")
            try:
                temporary.write_bytes(content)
                os.replace(temporary, self.settings.documents / name)
            finally:
                temporary.unlink(missing_ok=True)
            self.index = candidate
        return {"source": name, "deduplicated": False, **self.info()}

    def ask(self, question: str, mode: str = "hybrid", log: bool = True):
        started = time.perf_counter()
        result = {"id": uuid.uuid4().hex, "created": datetime.now(timezone.utc).isoformat(),
                  "provider": self.settings.provider, "retrieval_mode": mode,
                  "status": "abstained", "answer": "I could not find enough evidence to answer this question.",
                  "claims": [], "sources": [], "retrieval_ms": 0.0, "generation_ms": 0.0,
                  "usage": {"input_tokens": 0, "output_tokens": 0, "attempts": 0}}
        # Serializes local model encode calls and gives each request one complete snapshot.
        with self.lock:
            index = self.index
            result["index_version"] = index.fingerprint
            hits = index.search(question, mode)
            sufficient = index.sufficient(hits)
        result["sources"] = hits
        result["retrieval_ms"] = (time.perf_counter() - started) * 1000
        if sufficient:
            generation_start = time.perf_counter()
            if self.settings.provider == "extractive":
                result.update(status="evidence", answer="Relevant excerpts found. Read the source text below.")
                result["claims"] = [{"text": hits[0]["text"], "quote": hits[0]["text"], "source_id": hits[0]["id"]}]
            else:
                try:
                    answer, usage = generate(question, hits, self.settings)
                    result["usage"] = usage
                    if answer.answerable:
                        result.update(status="answered", answer="\n\n".join(claim.text for claim in answer.claims),
                                      claims=[claim.model_dump() for claim in answer.claims])
                except GenerationError as error:
                    result.update(status="error", answer=str(error), usage=error.usage)
            result["generation_ms"] = (time.perf_counter() - generation_start) * 1000
        result["total_ms"] = (time.perf_counter() - started) * 1000
        result["cost_usd"] = estimate_cost(self.settings, result["usage"])
        if log:
            self.telemetry.record(result)
        return result
