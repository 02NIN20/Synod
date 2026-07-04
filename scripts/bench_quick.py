"""Single-run benchmark per model for quick comparison."""

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

async def run_model(model: str) -> dict:
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
            continue
        with open(filepath) as f:
            code = f.read()
        truth = GROUND_TRUTH[filename]
        print(f"\n  {filename}...", end=" ", flush=True)

        request = ReviewRequest(code=code, filename=filename, language="python")
        response = await council.review(request)
        found_cwes = {f.cwe for f in response.findings if f.cwe}
        precision, recall, f1 = compute_metrics(found_cwes, truth["expected_cwes"])
        results[filename] = {
            "total_findings": response.total_findings,
            "tokens": response.tokens_used,
            "time_s": response.time_seconds,
            "precision": round(precision, 3),
            "recall": round(recall, 3),
            "f1": round(f1, 3),
            "found_cwes": sorted(found_cwes),
        }
        print(f"P={precision:.0%} R={recall:.0%} F1={f1:.0%} t={response.time_seconds:.0f}s")
        sys.stdout.flush()

    return results

async def main():
    models = [
        "qwen3.7-plus-2026-05-26",
        "qwen3.7-max-2026-05-20",
    ]
    # Also redo coder-plus with 1 run for consistency
    # models.insert(0, "qwen3-coder-plus-2025-07-22")

    all_results = {}
    for model in models:
        all_results[model] = await run_model(model)

    print("\n\n" + "=" * 60)
    print("COMPARISON TABLE (single run per model)")
    print("=" * 60)

    header = f"{'Sample':<25} {'Metric':<10}"
    for m in models:
        header += f" {m[:25]:<25}"
    print(header)

    for filename in sorted(GROUND_TRUTH.keys()):
        for metric in ["precision", "recall", "f1", "time_s", "tokens"]:
            row = f"{filename:<25} {metric:<10}"
            for m in models:
                if filename in all_results.get(m, {}):
                    val = all_results[m][filename].get(metric, "-")
                    row += f" {str(val):<25}"
                else:
                    row += f" {'-':<25}"
            print(row)

    outpath = os.path.join(os.path.dirname(__file__), "bench_quick_results.json")
    with open(outpath, "w") as f:
        json.dump(all_results, f, indent=2)
    print(f"\nSaved to {outpath}")

if __name__ == "__main__":
    asyncio.run(main())
