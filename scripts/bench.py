"""Formal benchmark: 3 runs per sample, precision/recall/F1 by category."""

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

GROUND_TRUTH = {
    "vulnerable_code.py": {
        "category": "security",
        "expected_cwes": {"CWE-798", "CWE-89", "CWE-78", "CWE-94"},
        "expected_count": 5,
        "note": "creds, SQLi, os.system, subprocess shell, eval",
    },
    "xss_app.py": {
        "category": "security",
        "expected_cwes": {"CWE-79"},
        "expected_count": 3,
        "note": "reflected XSS in greet, comment, search endpoints",
    },
    "path_traversal.py": {
        "category": "security",
        "expected_cwes": {"CWE-22"},
        "expected_count": 3,
        "note": "read_file, delete_file, serve_static without sanitization",
    },
    "csrf_missing.py": {
        "category": "security",
        "expected_cwes": {"CWE-352"},
        "expected_count": 2,
        "note": "transfer_money, change_email without CSRF token",
    },
    "insecure_deserialize.py": {
        "category": "security",
        "expected_cwes": {"CWE-502"},
        "expected_count": 3,
        "note": "pickle.loads x2, yaml.Loader",
    },
    "quality_sample.py": {
        "category": "quality",
        "expected_cwes": set(),
        "expected_count": 0,
        "note": "zero security vulns, only quality issues",
    },
    "coupling_sample.py": {
        "category": "quality",
        "expected_cwes": set(),
        "expected_count": 0,
        "note": "zero security vulns, tight coupling, deep nesting",
    },
}

NUM_RUNS = 3


def compute_metrics(found_cwes, expected_cwes):
    true_positives = found_cwes & expected_cwes
    false_positives = found_cwes - expected_cwes
    false_negatives = expected_cwes - found_cwes

    tp = len(true_positives)
    fp = len(false_positives)
    fn = len(false_negatives)

    precision = tp / (tp + fp) if (tp + fp) > 0 else 1.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 1.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

    return precision, recall, f1, true_positives, false_positives, false_negatives


def mean_std(values):
    n = len(values)
    m = sum(values) / n
    v = sum((x - m) ** 2 for x in values) / n
    return m, math.sqrt(v)


async def run_bench():
    llm = QwenClient()
    council = Council(llm)

    results = {}  # filename -> list of per-run dicts

    for filename in sorted(GROUND_TRUTH.keys()):
        filepath = os.path.join(SAMPLES_DIR, filename)
        if not os.path.exists(filepath):
            print(f"SKIP {filename}: file not found")
            continue

        with open(filepath) as f:
            code = f.read()

        truth = GROUND_TRUTH[filename]
        print(f"\n=== {filename} ({truth['category']}) ===")

        runs = []
        for run_idx in range(NUM_RUNS):
            request = ReviewRequest(code=code, filename=filename, language="python")
            response = await council.review(request)

            found_cwes = {f.cwe for f in response.findings if f.cwe}
            precision, recall, f1, tp_set, fp_set, fn_set = compute_metrics(
                found_cwes, truth["expected_cwes"]
            )

            run_data = {
                "run": run_idx + 1,
                "total_findings": response.total_findings,
                "tokens": response.tokens_used,
                "time_s": response.time_seconds,
                "found_cwes": sorted(found_cwes),
                "true_positives": sorted(tp_set),
                "false_positives": sorted(fp_set),
                "false_negatives": sorted(fn_set),
                "precision": round(precision, 3),
                "recall": round(recall, 3),
                "f1": round(f1, 3),
            }
            runs.append(run_data)
            print(
                f"  run {run_idx+1}: P={precision:.1%} R={recall:.1%} "
                f"F1={f1:.1%} tok={response.tokens_used} t={response.time_seconds:.1f}s "
                f"FP={sorted(fp_set)} FN={sorted(fn_set)}"
            )

        results[filename] = runs

    # Aggregate
    print("\n" + "=" * 70)
    print("BENCHMARK SUMMARY")
    print("=" * 70)

    header = f"{'Sample':<28} {'Category':<10} {'Precision':<12} {'Recall':<12} {'F1':<12} {'Tokens':<10} {'Time(s)':<10}"
    print(header)
    print("-" * 90)

    rows = []
    for filename in sorted(GROUND_TRUTH.keys()):
        if filename not in results:
            continue
        runs = results[filename]
        cat = GROUND_TRUTH[filename]["category"]

        precisions = [r["precision"] for r in runs]
        recalls = [r["recall"] for r in runs]
        f1s = [r["f1"] for r in runs]
        tokens = [r["tokens"] for r in runs]
        times = [r["time_s"] for r in runs]

        p_m, p_s = mean_std(precisions)
        r_m, r_s = mean_std(recalls)
        f_m, f_s = mean_std(f1s)
        t_m, _ = mean_std(tokens)
        ti_m, _ = mean_std(times)

        p_str = f"{p_m:.3f}±{p_s:.3f}"
        r_str = f"{r_m:.3f}±{r_s:.3f}"
        f_str = f"{f_m:.3f}±{f_s:.3f}"
        row = f"{filename:<28} {cat:<10} {p_str:<12} {r_str:<12} {f_str:<12} {t_m:<10.0f} {ti_m:<10.1f}"
        rows.append(row)
        print(row)

    # Category averages (macro)
    for cat in ("security", "quality"):
        cat_rows = [r for f, r in zip(sorted(GROUND_TRUTH.keys()), rows)
                    if f in results and GROUND_TRUTH[f]["category"] == cat]
        if cat_rows:
            print("-" * 90)
            all_p = [runs[fn]["precision"] for fn, runs in results.items()
                     if fn in GROUND_TRUTH and GROUND_TRUTH[fn]["category"] == cat]
            all_r = [runs[fn]["recall"] for fn, runs in results.items()
                     if fn in GROUND_TRUTH and GROUND_TRUTH[fn]["category"] == cat]
            all_f = [runs[fn]["f1"] for fn, runs in results.items()
                     if fn in GROUND_TRUTH and GROUND_TRUTH[fn]["category"] == cat]

            flat_p = [v for run in all_p for v in ([run] if isinstance(run, (int, float)) else run)]
            flat_r = [v for run in all_r for v in ([run] if isinstance(run, (int, float)) else run)]
            flat_f = [v for run in all_f for v in ([run] if isinstance(run, (int, float)) else run)]

            p_m, p_s = mean_std(flat_p)
            r_m, r_s = mean_std(flat_r)
            f_m, f_s = mean_std(flat_f)

            all_tokens = [r["tokens"] for fn, runs in results.items()
                          if fn in GROUND_TRUTH and GROUND_TRUTH[fn]["category"] == cat
                          for r in runs]
            all_times = [r["time_s"] for fn, runs in results.items()
                         if fn in GROUND_TRUTH and GROUND_TRUTH[fn]["category"] == cat
                         for r in runs]
            avg_tok = sum(all_tokens) / len(all_tokens)
            avg_tim = sum(all_times) / len(all_times)

            print(f"{'Avg (' + cat + ')':<28} {'':<10} {p_m:.3f}±{p_s:.3f}    {r_m:.3f}±{r_s:.3f}    {f_m:.3f}±{f_s:.3f}    {avg_tok:<10.0f} {avg_tim:<10.1f}")

    print("=" * 90)


if __name__ == "__main__":
    asyncio.run(run_bench())
