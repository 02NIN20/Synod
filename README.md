# Synod

Multi-agent code review council, powered by Qwen LLM.  
**Cartographer** maps structure → **Inspector** + **Sentinel** analyze → **Arbiter** deduplicates → **Smith** (optional) generates fixes.

> **Note:** Synod is not an MCP server. It exposes a standard REST API
> (FastAPI). MCP integration is a possible future wrapper, not implemented.

## Architecture

<p align="center">
  <img src="docs/architecture.png" alt="Synod architecture" width="700">
</p>

## How It Works

Synod runs a sequential pipeline of specialized LLM agents. The **Cartographer** first maps the code's structure (modules, dependencies, entry points), then **Inspector** (code quality) and **Sentinel** (security, CWE-mapped) analyze in parallel. **Arbiter** deduplicates and validates findings by consensus. Optionally, **Smith** generates fixes validated by Sentinel in a retry loop.

## Quickstart

```bash
git clone https://github.com/02NIN20/Synod.git
cd Synod
cp .env.example .env
# edit .env — set your DASHSCOPE_API_KEY
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

**Option A — local development:**
```bash
uvicorn app.main:app --reload
```

**Option B — Docker:**
```bash
docker compose up -d --build
```

**Run a review:**
```bash
./synod review tests/samples/vulnerable_code.py
./synod review tests/samples/vulnerable_code.py --fix   # with fix loop
```

## CLI Usage

| Command | Description |
|---------|-------------|
| `./synod review <file>` | Full multi-agent code review |
| `./synod chat [message]` | Interactive or one-shot chat (code → review, text → LLM reply) |
| `./synod scan <dir>` | Scan a directory, review every file |
| `./synod health` | Check if the API is running |

### Flags

| Flag | Applies to | Description |
|------|------------|-------------|
| `--fix` | review, scan | Enable fix loop (Smith + Sentinel validation) |
| `--show-code` | review | Print the source code before review |
| `--url` | all | API base URL (default: `http://localhost:8000`) |
| `--ext` | scan | File extension filter (default: `.py`) |
| `--limit` | scan | Max files to scan (0 = unlimited) |
| `--yes` | scan | Skip confirmation prompt |

### Chat REPL commands

Inside `./synod chat`:

| Command | Description |
|---------|-------------|
| `/review <file>` | Run a full council review on a file |
| `/scan <dir>` | Scan a directory |
| `/exit` | Quit |

## Benchmark

### Primary model — `qwen3-coder-plus-2025-07-22` (3 runs per sample)

**TP**: finding with correct CWE AND line within ±2 lines.  
**FP**: finding with no ground-truth match.  
**FN**: ground-truth bug with no finding.

| Sample | Category | Precision | Recall | F1 | Tokens | Time(s) |
|--------|----------|-----------|--------|----|--------|---------|
| vulnerable_code.py | security | 1.000±0.000 | 1.000±0.000 | 1.000±0.000 | 38706 | 20.9 |
| xss_app.py | security | 1.000±0.000 | 1.000±0.000 | 1.000±0.000 | 45484 | 15.9 |
| insecure_deserialize.py | security | 1.000±0.000 | 1.000±0.000 | 1.000±0.000 | 15952 | 14.4 |
| csrf_missing.py | security | 1.000±0.000 | 0.667±0.471 | 0.667±0.471 | 10916 | 13.6 |
| path_traversal.py | security | 1.000±0.000 | 0.000±0.000 | 0.000±0.000 | 21518 | 15.6 |
| **Avg (security)** | | **1.000** | **0.733** | **0.733** | 26515 | 16.1 |
| quality_sample.py | quality | 1.000±0.000 | 1.000±0.000 | 1.000±0.000 | 29954 | 11.2 |
| coupling_sample.py | quality | 1.000±0.000 | 1.000±0.000 | 1.000±0.000 | 4743 | 14.0 |
| clean_sample.py | quality | 1.000±0.000 | 1.000±0.000 | 1.000±0.000 | 4587 | 10.0 |
| **Avg (quality)** | | **1.000** | **1.000** | **1.000** | 17348 | 12.6 |

**Known limitations:**
- CWE-22 (path traversal): 0.000 recall — the model does not detect it even with explicit examples.
- CWE-352 (CSRF): ≈0.667 recall — inconsistent across runs due to LLM sampling variance.
- Results are stochastic; individual runs may vary.

### Model comparison — all models, single run per sample

| Sample | coder-plus (F1) | 3.5-plus (F1) | 3.7-plus (F1) | 3.7-max (F1) |
|--------|----------------:|--------------:|--------------:|--------------:|
| clean_sample.py | 1.000 | 1.000 | 1.000 | 1.000 |
| coupling_sample.py | 1.000 | 1.000 | 1.000 | 1.000 |
| quality_sample.py | 1.000 | 1.000 | 1.000 | 1.000 |
| csrf_missing.py | 1.000 | 1.000 | **0.000** | 1.000 |
| insecure_deserialize.py | 1.000 | **0.000** | **0.000** | 1.000 |
| vulnerable_code.py | 1.000 | **0.000** | **0.000** | **0.000** |
| xss_app.py | 1.000 | — | **0.000** | **0.000** |
| path_traversal.py | 1.000 | **0.000** | **0.000** | **0.000** |
| **Security avg** | **1.000** | **0.200** | **0.000** | **0.400** |
| **Quality avg** | **1.000** | **1.000** | **1.000** | **1.000** |
| **Avg time (s)** | **14.4** | **215.0** | **189.5** | **190.3** |

**Zero-F1 cells** indicate agent JSON-output failures (Inspector/Sentinel return `None` — model refuses or fails to produce structured JSON). This is a systematic issue with the newer-tier models when used inside Synod's multi-agent architecture.

Earlier clean single-run tests (before rate limiting, `vulnerable_code.py` only) showed all models capable of finding issues:

| Model | Findings | Critical | High | Tokens | Time (s) |
|-------|----------:|--------:|-----:|------:|---------:|
| qwen3-coder-plus-2025-07-22 | 8 | 3 | 4 | 2638 | 21.8 |
| qwen3.5-plus-2026-04-20 | 8 | 4 | 4 | 2913 | 23.0 |
| qwen3.7-plus-2026-05-26 | **9** | **7** | 2 | 2556 | **18.9** |
| qwen3.7-max-2026-05-20 | 8 | 5 | 3 | 2619 | **14.9** |

**Recommendation:** stick with `qwen3-coder-plus-2025-07-22` — it is the only model with 100% agent reliability across all samples. Newer-tier models (3.5-plus, 3.7-plus, 3.7-max) have inconsistent structured-output compliance, causing agent failures in ~60% of security reviews.

## API Reference

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/review` | POST | Full council code review |
| `/api/v1/chat` | POST | Chat with intent routing (code → council, text → LLM) |
| `/health` | GET | Health check |

### `/api/v1/review`

```json
{
  "code": "import os\nos.system('ls')",
  "filename": "example.py",
  "enable_fix_loop": false
}
```

### `/api/v1/chat`

```json
{
  "message": "What is a lambda?",
  "history": []
}
```

If `message` looks like code, the endpoint runs the council and returns summarized findings.  
Otherwise, it replies directly via Qwen LLM with conversation `history` for context.

## Tech Stack

| Layer | Technology |
|-------|------------|
| Framework | FastAPI (Python 3.12) |
| LLM | Qwen Cloud — `qwen3-coder-plus-2025-07-22` |
| CLI | Typer + Rich + httpx |
| Container | Docker, docker-compose |
| Deployment | ECS |

## Roadmap

- **Semgrep pre-filter** — static analysis pass before LLM agents to reduce cost and ground findings
- **Episodic/semantic memory** — remember past reviews across sessions for context
- **Weighted voting** — Arbiter uses confidence × severity × corroboration for ranking
- **GitHub PR integration** — automatic review comments on pull requests
- **Multi-language** — expand beyond Python (JS/TS, Go, Rust, Java)
- **CI/CD integration** — GitHub Action for automated PR review

## Extensibility

- **New agents**: subclass `BaseAgent`, implement `analyze()`, add to `AgentRole` enum, register in `Council.review()`.
- **New vulnerability classes**: add CWE patterns to Sentinel's `SYSTEM_PROMPT`.
- **LLM backends**: swap `QwenClient` for any OpenAI-compatible provider.
- **Arbiter strategies**: replace or compose dedup/consensus logic.

## License

MIT
