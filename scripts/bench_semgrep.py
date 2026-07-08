"""Benchmark: single-agent vs Synod vs Semgrep+LLM.

Single-agent: one direct LLM call with Sentinel's prompt (no Cartographer,
no Arbiter, no semgrep). Gives a fair apples-to-apples comparison against
the full council pipeline.
"""

import argparse
import asyncio
import json
import math
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.llm.qwen_client import QwenClient
from app.orchestrator.council import Council
from app.models.schemas import ReviewRequest, Finding, AgentRole, Severity, FindingSource
import app.orchestrator.council as council_mod

# Save original semgrep reference for restoration in LLM-only runs
council_mod._original_run_semgrep = council_mod.run_semgrep

SAMPLES_DIR = os.path.join(os.path.dirname(__file__), "..", "tests", "samples")

SINGLE_AGENT_PROMPT = """You are a security agent reviewing code.
Detect vulnerabilities: OWASP Top 10, CWE-mapped issues. Max 5 findings total.

Explicitly check every occurrence of these patterns, do not skip any:
- os.system, os.popen, subprocess.* (with or without shell=True) -> command injection (CWE-78)
- eval, exec, pickle.loads, yaml.load without SafeLoader -> code injection (CWE-94/502)
- string formatting/concatenation in SQL queries -> SQL injection (CWE-89)
- hardcoded credentials, API keys, tokens -> CWE-798
- path/file operations using unsanitized/user-controlled input -> path traversal (CWE-22)
- state-changing POST/PUT/DELETE routes with no CSRF token validation -> CWE-352
- unescaped user input rendered into HTML/templates -> XSS (CWE-79)

If multiple instances of the same vulnerability class exist, report the most
severe or representative one and mention others exist in detail.

Only report findings you are confident about. If a pattern is ambiguous or
you are not certain it is exploitable, do not report it. Do not flag
architecture, coupling, or style issues — that is out of scope.

Output strict JSON list:
[{"title": "...", "detail": "...", "impact": "critical|high|medium|low",
  "proposal": "...", "line_number": N, "cwe": "CWE-XX"}]
"""


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

DEFAULT_NUM_RUNS = 1
AVG_TOKENS_PER_CALL = 28000


def compute_metrics(findings, truth):
    """Compute precision/recall/F1 over CWEs, matching lines within ±2."""
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


async def run_single_agent(model: str, code: str, filename: str) -> tuple[list[Finding], int]:
    """Run one direct LLM call as single-agent baseline with extended timeout."""
    import asyncio, json
    from openai import AsyncOpenAI

    user_prompt = f"Review this code in file '{filename}':\n\n```{filename}\n{code}\n```"

    single_client = AsyncOpenAI(
        api_key=os.environ.get("DASHSCOPE_API_KEY", ""),
        base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
        timeout=120.0,
        max_retries=0,
    )
    try:
        response = await asyncio.wait_for(
            single_client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": SINGLE_AGENT_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
            ),
            timeout=120.0,
        )
        text = response.choices[0].message.content
        tokens = response.usage.total_tokens if response.usage else 0
    except Exception:
        return [], 0

    findings = []
    try:
        items = json.loads(text or "[]")
    except Exception:
        return [], tokens
    for item in items:
        try:
            impact_str = item.get("impact", "medium")
            impact = Severity(impact_str)
        except Exception:
            impact = Severity.MEDIUM
        finding = Finding(
            id=str(hash((item.get("title", ""), item.get("line_number")))),
            agent=AgentRole.SENTINEL,
            title=item.get("title", "Unknown"),
            detail=item.get("detail", ""),
            impact=impact,
            proposal=item.get("proposal"),
            line_number=item.get("line_number"),
            cwe=item.get("cwe"),
            source=FindingSource.LLM,
        )
        findings.append(finding)
    return findings, tokens


async def run_condition(
    model: str,
    agent_model: str,
    condition: str,
    samples: list[str] | None = None,
    num_runs: int = DEFAULT_NUM_RUNS,
    result_file: str | None = None,
) -> dict:
    """Run selected samples for one condition."""
    print(f"\n{'='*60}")
    print(f"CONDITION: {condition} ({num_runs} run(s)/sample)")
    print(f"MODEL: {model}  AGENT_MODEL: {agent_model}")
    print(f"{'='*60}")

    if condition == "LLM-only":
        council_mod.run_semgrep = lambda code, filename: []
    else:
        council_mod.run_semgrep = council_mod._original_run_semgrep

    original_agent_model = council_mod.QWEN_AGENT_MODEL
    council_mod.QWEN_AGENT_MODEL = agent_model
    try:
        llm = QwenClient(model=model)
        council = Council(llm)
    finally:
        council_mod.QWEN_AGENT_MODEL = original_agent_model

    sample_names = sorted(samples if samples else GROUND_TRUTH.keys())
    results = {}
    total_tokens = 0
    total_time = 0.0

    for filename in sample_names:
        filepath = os.path.join(SAMPLES_DIR, filename)
        if not os.path.exists(filepath):
            print(f"SKIP {filename}: file not found")
            continue
        if filename not in GROUND_TRUTH:
            print(f"SKIP {filename}: no ground truth")
            continue

        with open(filepath) as f:
            code = f.read()

        truth = GROUND_TRUTH[filename]
        print(f"\n  --- {filename} ({truth['category']}) ---")

        runs = []
        for run_idx in range(num_runs):
            t0 = time.time()
            errors = []

            if condition == "single-agent":
                findings, response_tokens = await run_single_agent(agent_model, code, filename)
                elapsed = time.time() - t0
                semgrep_count = 0
                llm_count = len(findings)
            else:
                request = ReviewRequest(code=code, filename=filename, language="python")
                try:
                    response = await council.review(request)
                    findings = response.findings
                    elapsed = time.time() - t0
                    response_tokens = response.tokens_used
                    semgrep_count = sum(1 for f in findings if f.source == FindingSource.SEMGREP)
                    llm_count = sum(1 for f in findings if f.source == FindingSource.LLM)
                    errors = response.errors
                except Exception as exc:
                    elapsed = time.time() - t0
                    findings = []
                    response_tokens = 0
                    semgrep_count = 0
                    llm_count = 0
                    errors = [str(exc)]

            precision, recall, f1 = compute_metrics(findings, truth)
            found_cwes = {f.cwe for f in findings if f.cwe}

            run_data = {
                "run": run_idx + 1,
                "total_findings": len(findings),
                "tokens": response_tokens,
                "time_s": round(elapsed, 2),
                "found_cwes": sorted(found_cwes),
                "precision": round(precision, 3),
                "recall": round(recall, 3),
                "f1": round(f1, 3),
                "semgrep_count": semgrep_count,
                "llm_count": llm_count,
                "errors": errors,
            }
            runs.append(run_data)
            total_tokens += response_tokens
            total_time += elapsed
            print(
                f"    run {run_idx+1}: P={precision:.1%} R={recall:.1%} "
                f"F1={f1:.1%} tok={response_tokens} t={elapsed:.1f}s "
                f"findings={len(findings)} (semgrep={semgrep_count}, llm={llm_count})"
            )
            sys.stdout.flush()

            # Incremental save per sample
            if result_file:
                _save_incremental(result_file, condition, filename, runs)

        results[filename] = runs

    if condition == "LLM-only":
        council_mod.run_semgrep = council_mod._original_run_semgrep

    print(f"\n  Subtotal: {total_tokens} tokens, {total_time:.1f}s")
    return results


def _save_incremental(path: str, condition: str, filename: str, runs: list):
    """Append/update a sample result incrementally to the result file."""
    partial = {}
    if os.path.exists(path):
        try:
            partial = json.load(open(path))
        except Exception:
            partial = {}
    if condition not in partial:
        partial[condition] = {}
    partial[condition][filename] = runs
    with open(path, "w") as f:
        json.dump(partial, f, indent=2)


async def main():
    parser = argparse.ArgumentParser(description="Benchmark: single-agent vs Synod")
    parser.add_argument(
        "--sample",
        action="append",
        help="Sample filename to benchmark (can be repeated). Default: vulnerable_code.py.",
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=DEFAULT_NUM_RUNS,
        help=f"Number of runs per sample. Default: {DEFAULT_NUM_RUNS}.",
    )
    parser.add_argument(
        "--method",
        choices=["single-agent", "LLM-only", "Semgrep+LLM", "council", "all"],
        default="all",
        help="Condition to benchmark. 'all' runs single-agent + council (LLM-only + Semgrep+LLM).",
    )
    parser.add_argument(
        "--model",
        default=os.environ.get("QWEN_MODEL", "qwen3.6-plus-2026-04-02"),
        help="Main model. Default: QWEN_MODEL env var.",
    )
    parser.add_argument(
        "--agent-model",
        default=os.environ.get("QWEN_AGENT_MODEL", "qwen3-coder-next"),
        help="Agent model. Default: QWEN_AGENT_MODEL env var.",
    )
    parser.add_argument(
        "--estimate-cost",
        action="store_true",
        help="Print token cost estimate and exit without running.",
    )
    parser.add_argument(
        "--retry-sample",
        help="Retry a specific sample that previously failed.",
    )
    parser.add_argument(
        "--result-file",
        default=os.path.join(os.path.dirname(__file__), "bench_semgrep_results.json"),
        help="Result file path.",
    )
    args = parser.parse_args()

    conditions = []
    if args.method == "all":
        conditions = ["single-agent", "LLM-only", "Semgrep+LLM"]
    elif args.method == "council":
        conditions = ["LLM-only", "Semgrep+LLM"]
    else:
        conditions = [args.method]

    sample_names = args.sample if args.sample else ["vulnerable_code.py"]
    sample_names = [s for s in sample_names if s in GROUND_TRUTH]

    if args.estimate_cost:
        total_runs = len(sample_names) * args.runs * len(conditions)
        estimated_tokens = total_runs * AVG_TOKENS_PER_CALL
        print(f"Samples: {len(sample_names)} ({', '.join(sample_names)})")
        print(f"Runs: {total_runs}")
        print(f"Estimated tokens: ~{estimated_tokens:,}")
        print(f"At ~1M token budget: {estimated_tokens / 1_000_000:.2%} of quota")
        return

    all_results = {}

    for condition in conditions:
        try:
            results = await run_condition(
                args.model,
                args.agent_model,
                condition,
                samples=sample_names,
                num_runs=args.runs,
                result_file=args.result_file,
            )
            all_results[condition] = results
        except Exception as exc:
            print(f"\n  ERROR in condition '{condition}': {exc}")
            if args.retry_sample and args.retry_sample in sample_names:
                print(f"  Retrying only {args.retry_sample}...")
                results = await run_condition(
                    args.model,
                    args.agent_model,
                    condition,
                    samples=[args.retry_sample],
                    num_runs=args.runs,
                    result_file=args.result_file,
                )
                all_results[condition] = results

    # Print combined table
    if not all_results:
        return

    print("\n\n" + "=" * 120)
    print("BENCHMARK RESULTS")
    print("=" * 120)

    header = (
        f"{'Sample':<28} {'Method':<14} {'Precision':<12} {'Recall':<12} {'F1':<12} "
        f"{'Tokens':<10} {'Time(s)':<10} {'Semgrep':<8} {'LLM':<8}"
    )
    print(header)
    print("-" * 120)

    rows = []
    for filename in sample_names:
        for condition in conditions:
            if condition not in all_results or filename not in all_results[condition]:
                continue
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
                f"{filename:<28} {condition:<14} {p_m:.3f}±{p_s:.3f}  {r_m:.3f}±{r_s:.3f}  "
                f"{f_m:.3f}±{f_s:.3f}  {t_m:<6.0f}  {ti_m:<6.1f}  {s_m:<6.1f}  {l_m:<6.1f}"
            )
            rows.append(row)
            print(row)

    # Save final results
    with open(args.result_file, "w") as f:
        json.dump(all_results, f, indent=2)
    print(f"\nResults saved to {args.result_file}")


if __name__ == "__main__":
    asyncio.run(main())
