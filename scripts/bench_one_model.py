"""Run full benchmark for a single model and save results to JSON."""

import asyncio
import json
import math
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.llm.qwen_client import QwenClient
from app.orchestrator.council import Council
from app.models.schemas import ReviewRequest

SAMPLES_DIR = os.path.join(os.path.dirname(__file__), "..", "tests", "samples")
NUM_RUNS = 3

GROUND_TRUTH = {
    "vulnerable_code.py": {"category": "security", "expected_cwes": {"CWE-798", "CWE-89", "CWE-78", "CWE-94"}, "expected_count": 5},
    "xss_app.py": {"category": "security", "expected_cwes": {"CWE-79"}, "expected_count": 3},
    "path_traversal.py": {"category": "security", "expected_cwes": {"CWE-22"}, "expected_count": 3},
    "csrf_missing.py": {"category": "security", "expected_cwes": {"CWE-352"}, "expected_count": 2},
    "insecure_deserialize.py": {"category": "security", "expected_cwes": {"CWE-502"}, "expected_count": 3},
    "quality_sample.py": {"category": "quality", "expected_cwes": set(), "expected_count": 0},
    "coupling_sample.py": {"category": "quality", "expected_cwes": set(), "expected_count": 0},
    "clean_sample.py": {"category": "quality", "expected_cwes": set(), "expected_count": 0},
}

def compute_metrics(found_cwes, expected_cwes):
    tp = len(found_cwes & expected_cwes)
    fp = len(found_cwes - expected_cwes)
    fn = len(expected_cwes - found_cwes)
    precision = tp / (tp + fp) if (tp + fp) > 0 else 1.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 1.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    return precision, recall, f1

async def run_bench(model: str) -> dict:
    os.environ["QWEN_MODEL"] = model
    llm = QwenClient(model=model)
    council = Council(llm)
    print(f"\n{'='*60}")
    print(f"MODEL: {model}")
    print(f"{'='*60}")

    results = {}
    for filename in sorted(GROUND_TRUTH.keys()):
        filepath = os.path.join(SAMPLES_DIR, filename)
        if not os.path.exists(filepath):
            print(f"  SKIP {filename}: not found")
            continue
        with open(filepath) as f:
            code = f.read()
        truth = GROUND_TRUTH[filename]
        print(f"\n  --- {filename} ({truth['category']}) ---")

        runs = []
        for run_idx in range(NUM_RUNS):
            request = ReviewRequest(code=code, filename=filename, language="python")
            response = await council.review(request)
            found_cwes = {f.cwe for f in response.findings if f.cwe}
            precision, recall, f1 = compute_metrics(found_cwes, truth["expected_cwes"])
            runs.append({
                "run": run_idx + 1,
                "total_findings": response.total_findings,
                "tokens": response.tokens_used,
                "time_s": response.time_seconds,
                "precision": round(precision, 3),
                "recall": round(recall, 3),
                "f1": round(f1, 3),
            })
            print(f"    run {run_idx+1}: P={precision:.1%} R={recall:.1%} F1={f1:.1%} tok={response.tokens_used} t={response.time_seconds:.1f}s")
            # Flush
            sys.stdout.flush()

        results[filename] = runs
        # Incremental save
        safe_model = model.replace("-", "_").replace(".", "_")
        with open(f"/tmp/bench_{safe_model}.json", "w") as f:
            json.dump(results, f, indent=2)

    return results

if __name__ == "__main__":
    model = sys.argv[1] if len(sys.argv) > 1 else "qwen3-coder-plus-2025-07-22"
    results = asyncio.run(run_bench(model))
    safe_model = model.replace("-", "_").replace(".", "_")
    outpath = os.path.join(os.path.dirname(__file__), f"bench_{safe_model}.json")
    with open(outpath, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nResults saved to {outpath}")
