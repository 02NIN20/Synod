"""Formal before/after benchmark for the Semgrep pre-filter.

Two conditions per sample:
  - LLM-only: current Sentinel behavior, no semgrep (baseline)
  - Semgrep+LLM: hybrid pipeline with pre-filter enabled

3 runs per condition; reports mean ± std for Precision, Recall, F1 plus
tokens, time, and source breakdown.
"""

import asyncio
import json
import math
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.llm.qwen_client import QwenClient
from app.orchestrator.council import Council
from app.models.schemas import ReviewRequest, FindingSource
import app.tools.semgrep_scanner as semgrep_mod

SAMPLES_DIR = os.path.join(os.path.dirname(__file__), "..", "tests", "samples")

GROUND_TRUTH = {
    "vulnerable_code.py": {
        "category": "security",
        "expected_cwes": {"CWE-798", "CWE-89", "CWE-78", "CWE-94"},
        "issues": [
            {"cwe": "CWE-798", "lines": [8, 9]},
            {"cwe": "CWE-89", "lines": [16]},
            {"cwe": "CWE-78", "lines": [29, 34]},
            {"cwe": "CWE-94", "lines": [54]},
        ],
    },
    "xss_app.py": {
        "category": "security",
        "expected_cwes": {"CWE-79"},
        "issues": [
            {"cwe": "CWE-79", "lines": [10, 17, 24]},
        ],
    },
    "path_traversal.py": {
        "category": "security",
        "expected_cwes": {"CWE-22"},
        "issues": [
            {"cwe": "CWE-22", "lines": [6, 12, 17]},
        ],
    },
    "csrf_missing.py": {
        "category": "security",
        "expected_cwes": {"CWE-352"},
        "issues": [
            {"cwe": "CWE-352", "lines": [7, 16]},
        ],
    },
    "insecure_deserialize.py": {
        "category": "security",
        "expected_cwes": {"CWE-502"},
        "issues": [
            {"cwe": "CWE-502", "lines": [7, 11, 15]},
        ],
    },
    "quality_sample.py": {
        "category": "quality",
        "expected_cwes": set(),
        "issues": [],
    },
    "coupling_sample.py": {
        "category": "quality",
        "expected_cwes": set(),
        "issues": [],
    },
}

NUM_RUNS = 3


def compute_metrics(findings, truth):
    """Compute precision/recall/F1 over CWEs, matching lines within ±2.

    Aligns with the existing benchmark: only findings that carry a CWE are
    scored. Quality samples (expected_cwes empty) get perfect scores because
    there are no ground-truth security issues to miss.
    """
    expected_cwes = truth["expected_cwes"]
    truth_issues = truth["issues"]

    if not expected_cwes:
        return 1.0, 1.0, 1.0

    found_cwes = {f.cwe for f in findings if f.cwe}
    matched_cwes = set()
    false_positives = set()

    for f in findings:
        if not f.cwe:
            continue
        matched = False
        for issue in truth_issues:
            if f.cwe == issue["cwe"]:
                if f.line_number is None:
                    continue
                if any(abs(f.line_number - line) <= 2 for line in issue["lines"]):
                    matched = True
                    matched_cwes.add(f.cwe)
                    break
        if not matched:
            false_positives.add(f.cwe)

    # Remove matched CWEs from false positives even if they also appear off-line
    false_positives -= matched_cwes

    tp = len(matched_cwes)
    fp = len(false_positives)
    fn = len(expected_cwes - matched_cwes)

    precision = tp / (tp + fp) if (tp + fp) > 0 else 1.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 1.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

    return precision, recall, f1


def mean_std(values):
    n = len(values)
    m = sum(values) / n
    v = sum((x - m) ** 2 for x in values) / n
    return m, math.sqrt(v)


def source_breakdown(findings):
    semgrep = sum(1 for f in findings if f.source == FindingSource.SEMGREP)
    llm = sum(1 for f in findings if f.source == FindingSource.LLM)
    return {"semgrep": semgrep, "llm": llm}


async def run_condition(model: str, condition: str) -> dict:
    """Run all samples for one condition (LLM-only or Semgrep+LLM)."""
    print(f"\n{'='*60}")
    print(f"CONDITION: {condition} ({NUM_RUNS} runs/sample)")
    print(f"{'='*60}")

    # Toggle semgrep globally via monkey-patch for LLM-only condition.
    original_run_semgrep = semgrep_mod.run_semgrep
    if condition == "LLM-only":
        semgrep_mod.run_semgrep = lambda code, filename: []
    else:
        semgrep_mod.run_semgrep = original_run_semgrep

    llm = QwenClient(model=model)
    council = Council(llm)

    results = {}
    for filename in sorted(GROUND_TRUTH.keys()):
        filepath = os.path.join(SAMPLES_DIR, filename)
        if not os.path.exists(filepath):
            print(f"SKIP {filename}: file not found")
            continue

        with open(filepath) as f:
            code = f.read()

        truth = GROUND_TRUTH[filename]
        print(f"\n  --- {filename} ({truth['category']}) ---")

        runs = []
        for run_idx in range(NUM_RUNS):
            request = ReviewRequest(code=code, filename=filename, language="python")
            t0 = time.time()
            response = await council.review(request)
            elapsed = time.time() - t0

            precision, recall, f1 = compute_metrics(response.findings, truth)
            sources = source_breakdown(response.findings)
            found_cwes = {f.cwe for f in response.findings if f.cwe}

            run_data = {
                "run": run_idx + 1,
                "total_findings": response.total_findings,
                "tokens": response.tokens_used,
                "time_s": round(elapsed, 2),
                "found_cwes": sorted(found_cwes),
                "precision": round(precision, 3),
                "recall": round(recall, 3),
                "f1": round(f1, 3),
                "semgrep_count": sources["semgrep"],
                "llm_count": sources["llm"],
                "errors": response.errors,
            }
            runs.append(run_data)
            print(
                f"    run {run_idx+1}: P={precision:.1%} R={recall:.1%} "
                f"F1={f1:.1%} tok={response.tokens_used} t={elapsed:.1f}s "
                f"findings={response.total_findings} (semgrep={sources['semgrep']}, llm={sources['llm']})"
            )
            sys.stdout.flush()

        results[filename] = runs

    # Restore original semgrep function
    semgrep_mod.run_semgrep = original_run_semgrep
    return results


async def main():
    model = os.environ.get("QWEN_MODEL", "qwen3-coder-plus-2025-07-22")
    conditions = ["LLM-only", "Semgrep+LLM"]

    all_results = {}
    for condition in conditions:
        all_results[condition] = await run_condition(model, condition)

    # Print combined table
    print("\n\n" + "=" * 120)
    print("BENCHMARK RESULTS: LLM-only vs Semgrep+LLM")
    print("=" * 120)

    header = (
        f"{'Sample':<28} {'Method':<12} {'Precision':<12} {'Recall':<12} {'F1':<12} "
        f"{'Tokens':<10} {'Time(s)':<10} {'Semgrep':<8} {'LLM':<8}"
    )
    print(header)
    print("-" * 120)

    rows = []
    for filename in sorted(GROUND_TRUTH.keys()):
        for condition in conditions:
            runs = all_results[condition][filename]
            precisions = [r["precision"] for r in runs]
            recalls = [r["recall"] for r in runs]
            f1s = [r["f1"] for r in runs]
            tokens = [r["tokens"] for r in runs]
            times = [r["time_s"] for r in runs]
            semgrep_counts = [r["semgrep_count"] for r in runs]
            llm_counts = [r["llm_count"] for r in runs]

            p_m, p_s = mean_std(precisions)
            r_m, r_s = mean_std(recalls)
            f_m, f_s = mean_std(f1s)
            t_m, _ = mean_std(tokens)
            ti_m, _ = mean_std(times)
            s_m, _ = mean_std(semgrep_counts)
            l_m, _ = mean_std(llm_counts)

            row = (
                f"{filename:<28} {condition:<12} {p_m:.3f}±{p_s:.3f}  {r_m:.3f}±{r_s:.3f}  "
                f"{f_m:.3f}±{f_s:.3f}  {t_m:<6.0f}  {ti_m:<6.1f}  {s_m:<6.1f}  {l_m:<6.1f}"
            )
            rows.append(row)
            print(row)

    # Category averages
    print("\n" + "-" * 120)
    print("CATEGORY AVERAGES")
    print("-" * 120)
    for condition in conditions:
        for cat in ("security", "quality"):
            cat_files = [fn for fn in GROUND_TRUTH if GROUND_TRUTH[fn]["category"] == cat]
            flat_p, flat_r, flat_f, flat_tok, flat_tim = [], [], [], [], []
            for fn in cat_files:
                for run in all_results[condition][fn]:
                    flat_p.append(run["precision"])
                    flat_r.append(run["recall"])
                    flat_f.append(run["f1"])
                    flat_tok.append(run["tokens"])
                    flat_tim.append(run["time_s"])
            p_m, p_s = mean_std(flat_p)
            r_m, r_s = mean_std(flat_r)
            f_m, f_s = mean_std(flat_f)
            avg_tok = sum(flat_tok) / len(flat_tok)
            avg_tim = sum(flat_tim) / len(flat_tim)
            print(
                f"{('Avg (' + cat + ')'):<28} {condition:<12} {p_m:.3f}±{p_s:.3f}  "
                f"{r_m:.3f}±{r_s:.3f}  {f_m:.3f}±{f_s:.3f}  {avg_tok:<6.0f}  {avg_tim:<6.1f}"
            )

    # Save results
    outpath = os.path.join(os.path.dirname(__file__), "bench_semgrep_results.json")
    with open(outpath, "w") as f:
        json.dump(all_results, f, indent=2)
    print(f"\nResults saved to {outpath}")


if __name__ == "__main__":
    asyncio.run(main())
