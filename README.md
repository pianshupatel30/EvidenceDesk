# EvidenceDesk

A Python document Q&A project with a browser interface, hybrid retrieval, optional LLM answers, a 60-question evaluation harness, and SQLite request telemetry.

The default mode works without API keys or model downloads after Python dependencies are installed. It returns source excerpts. Enable an LLM to generate answers, and enable Sentence Transformers for semantic embeddings and optional cross-encoder reranking.

The included documents describe a fictional arts centre. They are neutral synthetic examples for learning and evaluation.

## Redesigned workspace

Charcoal navigation, warm ivory, burnt-orange controls, and lime accents frame a document-first workspace. The library supports filtering and indexed-passage previews, answers link back to those previews, and the Evaluation view can filter review cases. DM Sans and Instrument Serif are bundled locally with their SIL Open Font Licenses in `evidencedesk/static/fonts/`. The app has no external font request.

**Updating an older copy? Read [UPDATE.md](UPDATE.md) and extract into a fresh folder.**

## Start on Windows

1. Install Python 3.11 or 3.12 with the Python launcher or PATH option enabled.
2. Extract this entire ZIP into a folder such as `Documents\EvidenceDesk`.
3. Double-click `setup_and_run.bat`. Keep its terminal open. The first run downloads Python packages.
4. Open [http://127.0.0.1:8000](http://127.0.0.1:8000).
5. On subsequent runs, double-click `run.bat`.

To stop the server, press Ctrl+C in the terminal. Open the whole extracted folder in VS Code to inspect the code.

### Manual setup in PowerShell

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -m evidencedesk
```

Run these commands from the folder containing `requirements.txt`. Copy `.env.example` only when you do not already have a configured `.env`.

### macOS or Linux

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
cp .env.example .env
.venv/bin/python -m evidencedesk
```

## Try the complete workflow

1. Ask `How do I book a workshop?` and expand its retrieved passages.
2. Ask `What will the weather be tomorrow?` to exercise abstention.
3. Upload your own UTF-8 TXT, Markdown, or text PDF. Scanned PDFs require OCR before upload. Limits are 5 MB, 150 PDF pages, 400,000 extracted characters, and 100 documents.
4. Open Evaluation and run the benchmark. Expand the rows marked Review.
5. Open Activity to see request timings, outcomes, token usage, and cost estimates.

Uploads receive content-based names. Repeated uploads are deduplicated. Uploads and telemetry persist across restarts. To remove an uploaded document, stop the server, delete its `documents/user_*` file, and restart. The index is rebuilt at startup. The app uses one process and one shared corpus.

## How the retrieval works

| Stage | Implementation |
| --- | --- |
| Ingestion | Extract UTF-8 text or PDF page text and preserve source names and page numbers |
| Chunking | Windows of 180 whitespace-separated words with 35-word overlap |
| Keyword retrieval | BM25 with k1 = 1.5 and b = 0.75 |
| Default vector retrieval | TF-IDF unigrams and bigrams with cosine similarity |
| Optional semantic retrieval | Normalized Sentence Transformer embeddings and exact in-memory cosine search |
| Fusion | Reciprocal rank fusion with k = 60 over the top 20 candidates from each method |
| Reranking | Query term coverage added to fusion score, or an optional learned cross-encoder |
| Relevance gate | Top result must exceed both similarity and query-term coverage thresholds |
| Answering | Excerpts by default, or model-generated claims with validated source IDs and exact quotes |

TF-IDF matches vocabulary. Semantic embeddings add meaning-based similarity. The default coverage reranker is a heuristic. The separate cross-encoder option loads a learned relevance model. The small corpus uses in-memory retrieval and SQLite telemetry. A vector database would be a future scaling exercise.

## Enable generated answers with Ollama

Install Ollama, then download a model suitable for your computer. One small model option is `qwen2.5:3b`.

```powershell
ollama pull qwen2.5:3b
```

Keep the Ollama service running. Change `.env` and restart EvidenceDesk.

```dotenv
ED_PROVIDER=ollama
ED_OLLAMA_URL=http://localhost:11434
ED_OLLAMA_MODEL=qwen2.5:3b
```

The adapter calls `/api/chat` with a JSON schema and validates the result again with Pydantic. It rejects invented source IDs and quotes absent from the retrieved text. Model response validation failures are visible errors. Temporary HTTP failures and connection failures have at most one retry. Local model latency depends on the model and your hardware. API cost is recorded as zero for a local Ollama server, excluding hardware and electricity.

## Enable semantic embeddings and learned reranking

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-semantic.txt
```

Then set these values in `.env` and restart.

```dotenv
ED_VECTOR_BACKEND=sentence-transformers
ED_EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
ED_RERANKER=cross-encoder
ED_CROSS_ENCODER=cross-encoder/ms-marco-MiniLM-L-6-v2
```

First use downloads model weights and requires an internet connection. This installation includes PyTorch and can consume substantial disk space. Keep `ED_RERANKER=coverage` to use semantic embeddings with the lightweight reranker. Similarity and coverage thresholds need evaluation for your own corpus. Requiring lexical coverage can reject valid paraphrases even with semantic embeddings enabled.

## Optional cloud generation

Set `ED_PROVIDER=openai-compatible`, `ED_API_BASE`, `ED_API_KEY`, and `ED_MODEL` in `.env`. Choose a model/provider that supports Chat Completions, `response_format` with `json_object`, and `max_tokens`. Some reasoning models require different generation parameters. The generic adapter is not universal.

The adapter requests JSON and performs strict local schema validation. Each claim needs a source ID and an exact supporting quote. Set `ED_INPUT_PRICE` and `ED_OUTPUT_PRICE` from the provider's current USD price per million tokens. Empty prices produce an unknown cost. Retried requests also have unknown cost because earlier server usage may be unreported. Estimates exclude cached-token discounts, provider-specific fees, and local compute.

Cloud generation sends the question and retrieved passages to the configured provider. API keys stay in the backend environment. Do not commit `.env`. The bundled `.gitignore` excludes it.

## Evaluate

```powershell
.\.venv\Scripts\python.exe -m evidencedesk.evaluate
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

The default CLI evaluation runs retrieval only and saves `reports/live_evaluation.json`. The browser benchmark saves `data/evaluation.json`. Both compare keyword, vector, and hybrid retrieval on the same 60 questions. Reports retain individual questions, expected sources, retrieved sources, and gate decisions. The interface marks a saved report stale when the corpus or retrieval settings change.

To also evaluate the configured answer provider, run the following command. It can call the provider for up to 60 hybrid queries and incur cloud charges when cloud generation is configured.

```powershell
.\.venv\Scripts\python.exe -m evidencedesk.evaluate --with-generation
```

The generation report includes statuses, exact-quote validity, expected-phrase presence, usage, and costs. Expected-phrase matching is a basic diagnostic and can penalize valid paraphrases. Neither this check nor citation validation establishes semantic faithfulness. Review generated answers manually against their source passages before reporting answer-quality results.

Read `reports/BASELINE.md` for measured results and known failures. Read `LEARN.md` for a guided walkthrough.

## Run with Docker

```bash
docker build -t evidencedesk .
docker run --rm -p 127.0.0.1:8000:8000 -v evidencedesk-data:/app/data -v evidencedesk-documents:/app/documents evidencedesk
```

The container runs as an unprivileged user. These named volumes preserve uploaded documents and telemetry. The Docker image uses the default excerpt mode. Pass environment variables when configuring a provider. A host Ollama service needs a host-reachable address from inside the container.

This project is a local, single-user portfolio application. Public deployment requires authentication, per-user data isolation, rate limits, managed storage, upload isolation, and deployment-specific controls. The default command binds to your own computer. Container configuration is included for local deployment, and has not been executed in the build environment.

## Repository guide

| File | Responsibility |
| --- | --- |
| `evidencedesk/ingest.py` | Parsing, limits, and chunk provenance |
| `evidencedesk/retrieval.py` | BM25, vectors, fusion, reranking, relevance gate |
| `evidencedesk/providers.py` | Model adapters, schema and citation checks, cost estimates |
| `evidencedesk/pipeline.py` | Atomic index replacement, request orchestration |
| `evidencedesk/telemetry.py` | SQLite storage and latency summaries |
| `evidencedesk/evaluate.py` | Fixed-question comparisons and JSON reports |
| `evidencedesk/api.py` | FastAPI request validation and routes |
| `evidencedesk/static/` | Browser interface |
| `evaluation/questions.json` | 48 answerable and 12 unsupported questions |
| `tests/test_project.py` | Integration and regression tests |

The API schema is at `/openapi.json`. Request metrics contain IDs, timings, usage, and outcome metadata. They exclude raw questions, source text, and API keys. The database retains all request rows, while the dashboard summarizes the latest 1,000. Pipeline timings exclude telemetry writes and browser/network overhead. Uploaded source files remain on disk until removed.

## Known scope and validation

The free mode, API endpoints, persistence, document parsing, uploads, and evaluation were tested in the supplied build environment. The redesigned browser rendering could not be verified: local Chromium could not launch, and the separate preview browser could not reach the local server. JavaScript syntax, DOM element references, and local asset delivery were checked. Provider HTTP adapters and semantic model integration have contract tests using controlled test doubles. Live model generation and downloaded embedding/reranking models require your local configuration and were not exercised here. The batch scripts are unchanged from the earlier version; this update was not run on Windows. The automated test run used Linux and Python 3.12.

The synthetic sample set is small and authored with the corpus. Perfect retrieval on it cannot establish real-world accuracy. Query processing is oriented toward English. Prompt instructions plus schema and quote checks reduce specific failure modes, but do not guarantee resistance to prompt injection or unsupported conclusions. Document parsing runs in the app process and is intended for your own local files.

## Official references

- [Sentence Transformer encoding](https://www.sbert.net/docs/package_reference/sentence_transformer/model.html)
- [Ollama chat and JSON-schema format](https://docs.ollama.com/api/chat)
- [OpenAI structured outputs and JSON mode](https://developers.openai.com/api/docs/guides/structured-outputs)
