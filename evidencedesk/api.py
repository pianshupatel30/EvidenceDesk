import json
from contextlib import asynccontextmanager
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator
from typing import Literal

from .config import ROOT, Settings
from .evaluate import evaluate, evaluation_config, save_report
from .pipeline import Service


class Question(BaseModel):
    question: str = Field(min_length=3, max_length=1500)
    mode: Literal["keyword", "vector", "hybrid"] = "hybrid"

    @field_validator("question")
    @classmethod
    def nonblank(cls, value):
        if len(value.strip()) < 3:
            raise ValueError("Enter at least three non-space characters")
        return value.strip()


class Upload(BaseModel):
    filename: str = Field(min_length=1, max_length=200)
    content_base64: str = Field(max_length=7_000_000)


def create_app(settings=None):
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app):
        app.state.service = Service(settings)
        yield

    app = FastAPI(title="EvidenceDesk", version="2.0.0", lifespan=lifespan, docs_url=None, redoc_url=None)

    @app.middleware("http")
    async def local_origin(request: Request, call_next):
        if request.method in {"POST", "PUT", "DELETE"}:
            origin = request.headers.get("origin")
            if origin and urlparse(origin).netloc != request.headers.get("host"):
                return JSONResponse({"detail": "Cross-origin writes are disabled"}, status_code=403)
            if request.headers.get("sec-fetch-site") == "cross-site":
                return JSONResponse({"detail": "Cross-site writes are disabled"}, status_code=403)
            try:
                too_large = int(request.headers.get("content-length", "0")) > 7_100_000
            except ValueError:
                return JSONResponse({"detail": "Invalid Content-Length"}, status_code=400)
            if too_large:
                return JSONResponse({"detail": "Request too large"}, status_code=413)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'"
        return response

    @app.get("/")
    def home():
        return FileResponse(ROOT / "evidencedesk" / "static" / "index.html")

    @app.get("/api/health")
    def health():
        return {"status": "ok", **app.state.service.info()}

    @app.post("/api/ask")
    def ask(body: Question):
        return app.state.service.ask(body.question, body.mode)

    @app.get("/api/documents/{source}")
    def document_preview(source: str):
        service = app.state.service
        with service.lock:
            chunks = [chunk.to_dict() for chunk in service.index.chunks if chunk.source == source]
        if not chunks:
            raise HTTPException(status_code=404, detail="Document not found in this collection")
        return {"source": source, "chunks": chunks}

    @app.post("/api/documents")
    def upload(body: Upload):
        try:
            return app.state.service.upload(body.filename, body.content_base64)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    @app.get("/api/metrics")
    def metrics():
        return app.state.service.telemetry.summary()

    @app.get("/api/evaluation")
    def report():
        path = settings.database.parent / "evaluation.json"
        if not path.exists():
            path = ROOT / "reports" / "demo_evaluation.json"
        if not path.exists():
            return {"available": False}
        result = json.loads(path.read_text(encoding="utf-8"))
        result["available"] = True
        result["stale"] = (result["index_version"] != app.state.service.index.fingerprint
                           or result["config"] != evaluation_config(settings))
        return result

    @app.post("/api/evaluate")
    def run_evaluation():
        service = app.state.service
        questions = json.loads((ROOT / "evaluation" / "questions.json").read_text(encoding="utf-8"))
        with service.lock:
            result = evaluate(service, questions)
            save_report(result, settings.database.parent / "evaluation.json")
        return {**result, "available": True, "stale": False}

    app.mount("/static", StaticFiles(directory=ROOT / "evidencedesk" / "static"), name="static")
    return app
