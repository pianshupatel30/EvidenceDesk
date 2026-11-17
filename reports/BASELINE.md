# Measured baseline: arts-centre collection

Measured with 12 fictional arts-centre documents, 60 synthetic questions, TF-IDF vectors, coverage reranking, similarity threshold 0.16, and coverage threshold 0.45. Generation was disabled.

Index fingerprint `b8bae40a7c0576f9`. Run timestamp `2026-11-16T12:22:23.995156+00:00`.

| Method | Hit@5 | MRR@5 | Unsupported rejected | Answerable accepted | P95 retrieval |
| --- | --- | --- | --- | --- | --- |
| keyword | 100.0% | 0.955 | 75.0% | 79.2% | 1.00 ms |
| vector | 100.0% | 0.976 | 75.0% | 81.2% | 0.77 ms |
| hybrid | 100.0% | 0.965 | 75.0% | 79.2% | 0.85 ms |

All 48 answerable questions retrieved a relevant source in the top five. The hybrid relevance gate accepted 38 of those 48 and rejected 9 of 12 unsupported questions. The baseline exposes limitations of lexical similarity and query-term coverage. This small corpus does not establish a retrieval advantage for hybrid search.

## Hybrid review cases

| ID | Question | Expected | Gate |
| --- | --- | --- | --- |
| q001 | What time does the arts centre open on weekends? | Answerable | Rejected |
| q003 | When is the last gallery admission? | Answerable | Rejected |
| q006 | How many participants can join each workshop? | Answerable | Rejected |
| q008 | What is the minimum age for a workshop? | Answerable | Rejected |
| q015 | Can I transfer a late cancellation to a friend? | Answerable | Rejected |
| q018 | What benefits come with membership? | Answerable | Rejected |
| q024 | When are quiet visits available? | Answerable | Rejected |
| q026 | How long can I borrow a book? | Answerable | Rejected |
| q029 | How often does the gallery change exhibitions? | Answerable | Rejected |
| q047 | Where can I leave a large bag? | Answerable | Rejected |
| q053 | How much does annual membership cost? | Unsupported | Accepted |
| q055 | How many days does a workshop refund take to arrive? | Unsupported | Accepted |
| q056 | Who is the artist exhibiting next month? | Unsupported | Accepted |

For q055, the matching cancellation article mentions refunds but supplies no processing duration. Retrieving that source does not provide enough evidence to answer the timing question. Conversely, q001 asks about weekends while the document specifies Saturday and Sunday: the lexical gate rejects useful evidence.

Keep these failures visible when experimenting. Tune against a separate development set, and preserve untouched questions for subsequent evaluation.

## Reproduction

```bash
python -m evidencedesk.evaluate --output reports/reproduced.json
python -m unittest discover -s tests -v
```

Latency is a single-process CPU measurement after index construction. It excludes downloads, index build, and generation. Timings vary across machines.

## Checks for version 2

- Sixteen automated tests passed, covering retrieval, abstention, upload persistence, API validation, indexing, telemetry, model-adapter contracts, and the new indexed-document preview endpoint.
- JavaScript syntax, HTML element references, local static asset delivery, and all three suggested questions were checked.
- The bundled fonts include their SIL Open Font Licenses and are served locally.
- Browser visual review is unverified. Local Chromium could not launch in the build environment; the separate preview browser could not reach the local server.
- Live model calls, downloaded semantic models, Docker execution, and this update on Windows were not run here. Model adapters and semantic integration use controlled doubles in the tests.

## Build environment

- Python 3.12.14 on Linux.
- fastapi 0.141.1
- uvicorn 0.52.1
- pydantic 2.13.4
- numpy 2.3.5
- scikit-learn 1.8.0
- httpx 0.28.1
- pypdf 6.21.4
- python-dotenv 1.2.2
