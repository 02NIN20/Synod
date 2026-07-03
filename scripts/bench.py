"""Quick benchmark: run Synod against ground-truth samples, report precision/recall."""

import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.llm.qwen_client import QwenClient
from app.orchestrator.council import Council
from app.models.schemas import ReviewRequest

SAMPLES_DIR = os.path.join(os.path.dirname(__file__), "..", "tests", "samples")

GROUND_TRUTH = {
    "vulnerable_code.py": {
        "expected_cwes": {"CWE-798", "CWE-89", "CWE-78", "CWE-94"},
        "expected_count": 5,
        "note": "creds, SQLi, os.system, subprocess shell, eval",
    },
    "quality_sample.py": {
        "expected_cwes": set(),
        "expected_count": 0,
        "note": "zero security vulns, only quality issues",
    },
}


async def run_bench():
    llm = QwenClient()
    council = Council(llm)

    results = []

    for filename, truth in GROUND_TRUTH.items():
        filepath = os.path.join(SAMPLES_DIR, filename)
        if not os.path.exists(filepath):
            print(f"SKIP {filename}: file not found")
            continue

        with open(filepath) as f:
            code = f.read()

        request = ReviewRequest(code=code, filename=filename, language="python")
        response = await council.review(request)

        found_cwes = set()
        for f in response.findings:
            if f.cwe:
                found_cwes.add(f.cwe)

        true_positives = found_cwes & truth["expected_cwes"]
        false_positives = found_cwes - truth["expected_cwes"]
        false_negatives = truth["expected_cwes"] - found_cwes

        precision = len(true_positives) / (len(true_positives) + len(false_positives)) if (len(true_positives) + len(false_positives)) > 0 else 1.0
        recall = len(true_positives) / (len(true_positives) + len(false_negatives)) if (len(true_positives) + len(false_negatives)) > 0 else 1.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

        result = {
            "sample": filename,
            "total_findings": response.total_findings,
            "tokens": response.tokens_used,
            "time_s": response.time_seconds,
            "found_cwes": sorted(found_cwes),
            "true_positives": sorted(true_positives),
            "false_positives": sorted(false_positives),
            "false_negatives": sorted(false_negatives),
            "precision": round(precision, 3),
            "recall": round(recall, 3),
            "f1": round(f1, 3),
        }
        results.append(result)

        summary = f"{filename}: precision={precision:.1%} recall={recall:.1%} f1={f1:.1%}"
        print(summary)

    total_tokens = sum(r["tokens"] for r in results)
    total_time = sum(r["time_s"] for r in results)
    avg_f1 = sum(r["f1"] for r in results) / len(results) if results else 0

    print(f"\nTotal tokens: {total_tokens}")
    print(f"Total time: {total_time:.1f}s")
    print(f"Average F1: {avg_f1:.1%}")

    bench_data = {"results": results, "summary": {
        "total_tokens": total_tokens,
        "total_time_s": round(total_time, 2),
        "avg_f1": round(avg_f1, 3),
    }}
    print("\n--- Full results ---")
    print(json.dumps(bench_data, indent=2))


if __name__ == "__main__":
    asyncio.run(run_bench())
