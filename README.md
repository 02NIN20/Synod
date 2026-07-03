# Synod

Multi-agent code review council powered by Qwen LLM.

## Architecture

![Synod Architecture](docs/architecture.png)

## Agents

| Agent | Role |
|---|---|
| **Cartographer** | Maps modules, dependencies, entry points |
| **Inspector** | Code quality: anti-patterns, complexity |
| **Sentinel** | Security: OWASP, CWE-mapped vulnerabilities |
| **Arbiter** | Deduplication, evidence validation, consensus |
| **Smith** | Generates fixes (optional fix loop) |

## Quick Start

```bash
cp .env.example .env
# edit .env with your DASHSCOPE_API_KEY

pip install -r requirements.txt

uvicorn app.main:app --reload
```

Open http://localhost:8000/docs

## Docker

```bash
docker compose up --build
```

## Testing

```bash
pytest tests/ -v
```

## API

`POST /api/v1/review`

```json
{
  "code": "import os\nos.system('ls')",
  "language": "python",
  "enable_fix_loop": false
}
```

## Benchmark

3 runs per sample, reported as mean ± std. Methodology:
- **TP**: finding with correct CWE AND line within ±2 lines of the real bug.
- **FP**: finding that does not correspond to any ground-truth bug.
- **FN**: ground-truth bug that no finding covers.
- **Precision** = TP / (TP + FP), **Recall** = TP / (TP + FN), **F1** = 2·(P·R)/(P+R).

| Sample | Category | Precision | Recall | F1 | Tokens | Time(s) |
|---|---|---|---|---|---|---|
| vulnerable_code.py | security | 1.000±0.000 | 1.000±0.000 | 1.000±0.000 | 38706 | 20.9 |
| xss_app.py | security | 1.000±0.000 | 1.000±0.000 | 1.000±0.000 | 45484 | 15.9 |
| insecure_deserialize.py | security | 1.000±0.000 | 1.000±0.000 | 1.000±0.000 | 15952 | 14.4 |
| csrf_missing.py | security | 1.000±0.000 | 0.667±0.471 | 0.667±0.471 | 10916 | 13.6 |
| path_traversal.py | security | 1.000±0.000 | 0.000±0.000 | 0.000±0.000 | 21518 | 15.6 |
| **Avg (security)** | | **1.000** | **0.733** | **0.733** | 26515 | 16.1 |
| quality_sample.py | quality | 1.000±0.000 | 1.000±0.000 | 1.000±0.000 | 29954 | 11.2 |
| coupling_sample.py | quality | 1.000±0.000 | 1.000±0.000 | 1.000±0.000 | 4743 | 14.0 |
| **Avg (quality)** | | **1.000** | **1.000** | **1.000** | 17348 | 12.6 |

**Known limitations:**
- CWE-22 (path traversal) is undetected — the model does not recognize it reliably even with explicit examples.
- CWE-352 (CSRF) detection is inconsistent (≈67% recall) due to LLM sampling variance.
- Results are stochastic; individual runs may vary, especially with 5-finding caps per agent.

## Extensibility

Synod is designed for horizontal agent expansion:

- **New agents**: subclass `BaseAgent` in `app/agents/`, implement `analyze()`, add the role to `AgentRole` enum, and register it in `Council.review()`. No other wiring needed.
- **New languages**: pass `language` in `ReviewRequest`. Agents receive it in context; the prompt can be adapted per language.
- **New vulnerability classes**: add the CWE pattern to Sentinel's `SYSTEM_PROMPT`. No code changes required.
- **Arbiter rules**: replace or compose `Arbiter` strategies (e.g., weighted voting, confidence thresholds) by implementing the same interface.
- **LLM backends**: swap `QwenClient` for any OpenAI-compatible provider by implementing the same `complete(system, user) -> str` contract.
- **The fix loop** is opt-in (`enable_fix_loop`); it can be disabled entirely, run on a subset of severities, or extended to multi-round negotiation between Smith and Sentinel.
