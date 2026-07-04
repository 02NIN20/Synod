"""Run full benchmark across all 4 Qwen models and output a comparison table."""

import asyncio
import json
import os
import sys
import time

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

MODELS = [
    "qwen3-coder-plus-2025-07-22",
    "qwen3.5-plus-2026-04-20",
    "qwen3.7-plus-2026-05-26",
    "qwen3.7-max-2026-05-20",
]


def compute_metrics(found_cwes, expected_cwes):
    tp = len(found_cwes & expected_cwes)
    fp = len(found_cwes - expected_cwes)
    fn = len(expected_cwes - found_cwes)
    precision = tp / (tp + fp) if (tp + fp) > 0 else 1.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 1.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    return precision, recall, f1


def mean_std(values):
    n = len(values)
    m = sum(values) / n
    v = sum((x - m) ** 2 for x in values) / n
    return m, math.sqrt(v)


import math


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

        results[filename] = runs
    return results


async def main():
    all_results = {}
    for model in MODELS:
        all_results[model] = await run_bench(model)

    # Print comparison table
    print("\n\n" + "=" * 120)
    print("BENCHMARK COMPARISON — ALL MODELS")
    print("=" * 120)

    for filename in sorted(GROUND_TRUTH.keys()):
        print(f"\n{'─'*90}")
        print(f"  {filename}")
        print(f"{'─'*90}")
        header = f"  {'Model':<30} {'Precision':<12} {'Recall':<12} {'F1':<12} {'Tokens':<10} {'Time(s)':<10} {'Findings':<10}"
        print(header)
        print(f"  {'─'*88}")
        for model in MODELS:
            if filename not in all_results[model]:
                continue
            runs = all_results[model][filename]
            precisions = [r["precision"] for r in runs]
            recalls = [r["recall"] for r in runs]
            f1s = [r["f1"] for r in runs]
            tokens = [r["tokens"] for r in runs]
            times = [r["time_s"] for r in runs]
            findings = [r["total_findings"] for r in runs]

            p_m, p_s = mean_std(precisions)
            r_m, r_s = mean_std(recalls)
            f_m, f_s = mean_std(f1s)
            t_m, _ = mean_std(tokens)
            ti_m, _ = mean_std(times)
            fn_m, _ = mean_std(findings)

            print(f"  {model:<30} {p_m:.3f}±{p_s:.3f}   {r_m:.3f}±{r_s:.3f}   {f_m:.3f}±{f_s:.3f}   {t_m:<6.0f}   {ti_m:<6.1f}   {fn_m:<6.0f}")

    # Category averages
    print(f"\n{'='*120}")
    print("CATEGORY AVERAGES")
    print(f"{'='*120}")
    for cat in ("security", "quality"):
        cat_files = [fn for fn in GROUND_TRUTH if GROUND_TRUTH[fn]["category"] == cat]
        print(f"\n  [{cat.upper()}]")
        header = f"  {'Model':<30} {'Precision':<12} {'Recall':<12} {'F1':<12} {'Tokens':<10} {'Time(s)':<10}"
        print(header)
        print(f"  {'─'*80}")
        for model in MODELS:
            flat_p, flat_r, flat_f, flat_tok, flat_tim = [], [], [], [], []
            for fn in cat_files:
                if fn in all_results[model]:
                    for run in all_results[model][fn]:
                        flat_p.append(run["precision"])
                        flat_r.append(run["recall"])
                        flat_f.append(run["f1"])
                        flat_tok.append(run["tokens"])
                        flat_tim.append(run["time_s"])
            if flat_p:
                p_m, p_s = mean_std(flat_p)
                r_m, r_s = mean_std(flat_r)
                f_m, f_s = mean_std(flat_f)
                avg_tok = sum(flat_tok) / len(flat_tok)
                avg_tim = sum(flat_tim) / len(flat_tim)
                print(f"  {model:<30} {p_m:.3f}±{p_s:.3f}   {r_m:.3f}±{r_s:.3f}   {f_m:.3f}±{f_s:.3f}   {avg_tok:<6.0f}   {avg_tim:<6.1f}")

    # Save to JSON
    with open(os.path.join(os.path.dirname(__file__), "bench_results.json"), "w") as f:
        json.dump(all_results, f, indent=2, default=str)
    print(f"\n\nResults saved to scripts/bench_results.json")


if __name__ == "__main__":
    asyncio.run(main())
