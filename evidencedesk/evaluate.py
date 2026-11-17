import argparse
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from .config import ROOT, Settings
from .pipeline import Service


def evaluation_config(settings):
    return {name: getattr(settings, name) for name in ["vector_backend", "reranker", "embedding_model",
            "cross_encoder", "min_similarity", "min_coverage"]}


def evaluate(service, questions, with_generation=False):
    reports = []
    for mode in ["keyword", "vector", "hybrid"]:
        rows = []
        for item in questions:
            started = time.perf_counter()
            with service.lock:
                hits = service.index.search(item["question"], mode)
                accepted = service.index.sufficient(hits)
            ranks = [rank for rank, hit in enumerate(hits, 1) if hit["source"] in item["relevant_sources"]]
            row = {**item, "retrieved_sources": [hit["source"] for hit in hits],
                   "hit_at_5": bool(ranks), "reciprocal_rank": 1 / min(ranks) if ranks else 0,
                   "accepted": accepted, "latency_ms": (time.perf_counter() - started) * 1000,
                   "top_similarity": hits[0]["similarity"] if hits else 0,
                   "top_coverage": hits[0]["coverage"] if hits else 0}
            # Only hybrid generation is evaluated to limit deliberate provider use.
            if with_generation and mode == "hybrid":
                result = service.ask(item["question"], mode, log=False)
                claims = result["claims"]
                source_map = {hit["id"]: hit["text"] for hit in result["sources"]}
                row["generation"] = {"status": result["status"], "answer": result["answer"],
                    "expected_phrase_present": item["expected_phrase"].lower() in result["answer"].lower() if item["answerable"] else None,
                    "valid_citations": all(c["quote"] in source_map.get(c["source_id"], "") for c in claims) if claims else None,
                    "usage": result["usage"], "cost_usd": result["cost_usd"]}
            rows.append(row)
        positive = [row for row in rows if row["answerable"]]
        negative = [row for row in rows if not row["answerable"]]
        reports.append({"mode": mode, "hit_at_5": sum(row["hit_at_5"] for row in positive) / max(len(positive), 1),
                        "mrr_at_5": sum(row["reciprocal_rank"] for row in positive) / max(len(positive), 1),
                        "unanswerable_rejection_rate": sum(not row["accepted"] for row in negative) / max(len(negative), 1),
                        "answerable_acceptance_rate": sum(row["accepted"] for row in positive) / max(len(positive), 1),
                        "p95_retrieval_ms": float(np.percentile([row["latency_ms"] for row in rows], 95)), "rows": rows})
    return {"created": datetime.now(timezone.utc).isoformat(), "index_version": service.index.fingerprint,
            "config": evaluation_config(service.settings), "question_count": len(questions),
            "answerable_count": sum(q["answerable"] for q in questions), "with_generation": with_generation,
            "provider": service.settings.provider, "results": reports,
            "limitations": "Synthetic questions authored with the sample documents. Retrieval relevance gates do not establish answer correctness. Citation checks validate source IDs and exact quotes, not semantic entailment. TF-IDF is lexical. Local CPU timing excludes model downloads and index build time."}


def save_report(report, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    try:
        temporary.write_text(json.dumps(report, indent=2), encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description="Compare keyword, vector and hybrid retrieval")
    parser.add_argument("--questions", type=Path, default=ROOT / "evaluation" / "questions.json")
    parser.add_argument("--output", type=Path, default=ROOT / "reports" / "live_evaluation.json")
    parser.add_argument("--with-generation", action="store_true", help="Also call the configured model for hybrid queries. Cloud usage may incur charges.")
    args = parser.parse_args()
    report = evaluate(Service(Settings()), json.loads(args.questions.read_text(encoding="utf-8")), args.with_generation)
    save_report(report, args.output)
    for row in report["results"]:
        print(f"{row['mode']:8} Hit@5={row['hit_at_5']:.3f} MRR@5={row['mrr_at_5']:.3f} reject={row['unanswerable_rejection_rate']:.3f} accept={row['answerable_acceptance_rate']:.3f}")
    print(f"Saved {args.output}")


if __name__ == "__main__":
    main()
