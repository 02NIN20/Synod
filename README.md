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

3 runs per sample per condition, reported as mean ± std.  
**TP**: finding with correct CWE AND line within ±2 lines.  
**FP**: finding with no ground-truth match.  
**FN**: ground-truth bug with no finding.

| Sample | Category | Method | Precision | Recall | F1 | Tokens | Time(s) | Semgrep | LLM |
|--------|----------|--------|-----------|--------|----|--------|---------|---------|-----|
| vulnerable_code.py | security | LLM-only | 1.000±0.000 | 0.583±0.118 | 0.730±0.090 | 47663 | 31.1 | 0.0 | 8.7 |
| vulnerable_code.py | security | Semgrep+LLM | 1.000±0.000 | **0.917±0.118** | **0.952±0.067** | 48306 | 31.0 | 4.0 | 9.0 |
| xss_app.py | security | LLM-only | 1.000±0.000 | 1.000±0.000 | 1.000±0.000 | 60455 | 34.0 | 4.0 | 7.3 |
| xss_app.py | security | Semgrep+LLM | 0.667±0.236 | 1.000±0.000 | 0.778±0.157 | 60952 | 30.2 | 4.0 | 6.7 |
| insecure_deserialize.py | security | LLM-only | 1.000±0.000 | 1.000±0.000 | 1.000±0.000 | 20284 | 26.3 | 3.0 | 4.3 |
| insecure_deserialize.py | security | Semgrep+LLM | 1.000±0.000 | 1.000±0.000 | 1.000±0.000 | 20482 | 29.7 | 3.0 | 5.3 |
| csrf_missing.py | security | LLM-only | 1.000±0.000 | 0.333±0.471 | 0.333±0.471 | 12590 | 27.4 | 1.0 | 3.3 |
| csrf_missing.py | security | Semgrep+LLM | 1.000±0.000 | 0.333±0.471 | 0.333±0.471 | 12862 | 28.7 | 1.0 | 3.3 |
| path_traversal.py | security | LLM-only | 1.000±0.000 | 1.000±0.000 | 1.000±0.000 | 27379 | 29.3 | 1.0 | 3.0 |
| path_traversal.py | security | Semgrep+LLM | 1.000±0.000 | 1.000±0.000 | 1.000±0.000 | 27800 | 33.8 | 1.0 | 3.3 |
| **Avg (security)** | | LLM-only | **1.000** | 0.783 | 0.813 | 33674 | 29.6 | | |
| **Avg (security)** | | Semgrep+LLM | 0.933 | **0.850** | **0.813** | 34080 | 30.7 | | |
| quality_sample.py | quality | LLM-only | 1.000±0.000 | 1.000±0.000 | 1.000±0.000 | 36762 | 25.5 | 0.0 | 6.0 |
| quality_sample.py | quality | Semgrep+LLM | 1.000±0.000 | 1.000±0.000 | 1.000±0.000 | 37482 | 26.2 | 0.0 | 6.0 |
| coupling_sample.py | quality | LLM-only | 1.000±0.000 | 1.000±0.000 | 1.000±0.000 | 5480 | 29.2 | 0.0 | 6.7 |
| coupling_sample.py | quality | Semgrep+LLM | 1.000±0.000 | 1.000±0.000 | 1.000±0.000 | 5642 | 28.0 | 0.0 | 6.3 |
| **Avg (quality)** | | LLM-only | **1.000** | **1.000** | **1.000** | 21121 | 27.4 | | |
| **Avg (quality)** | | Semgrep+LLM | **1.000** | **1.000** | **1.000** | 21562 | 27.1 | | |

**Key findings:**
- **CWE-22 (path traversal)**: recall already at 1.000 in the LLM-only run; Semgrep+LLM keeps it at 1.000. The deterministic semgrep rule at line 6 provides a floor, but in this stochastic run the LLM also caught it.
- **CWE-352 (CSRF)**: no improvement from semgrep in this run (0.333±0.471 both). Semgrep's default CSRF rules are pattern-based and miss framework-specific CSRF validation; this class remains LLM-dependent.
- **CWE-89 / CWE-94 / CWE-798 / CWE-78** (`vulnerable_code.py`): the biggest win. Semgrep's deterministic rules for hardcoded secrets, SQL injection, eval, and command injection raise recall from 0.583 to 0.917 and F1 from 0.730 to 0.952.
- **CWE-79 (`xss_app.py`)**: precision dropped to 0.667 in the first Semgrep+LLM run because registry rules fired multiple overlapping hits on the same vulnerability (SSTI + raw-html-format on line 10, plus definition-line vs render-call lines). Root cause was direct injection of raw semgrep findings and insufficient dedup. Fixed by: (1) deduping semgrep hits by CWE+line cluster before passing to Sentinel, (2) removing direct semgrep injection so findings only survive if Sentinel validates them, (3) updating Sentinel's prompt to treat semgrep output as unvalidated candidates and drop anything it cannot confirm from the actual code. Re-verification benchmark for `xss_app.py` is pending API quota reset.
- **Quality samples**: semgrep contributes no findings and introduces no false positives.
- **Cost/latency**: token usage is essentially unchanged (+1.5% security avg); wall time increases by ~1s per sample because of the semgrep scan overhead. Semgrep reduces LLM token discovery load, but Sentinel still runs its full pass.

**Conclusion:** the Semgrep pre-filter is worth the added complexity for multi-bug files (`vulnerable_code.py` recall +57%) and provides a deterministic safety net for classes like path traversal and command injection. It does not help CSRF, which remains a known weakness. The xss_app precision regression has been addressed in code.

> **Note on re-verification:** the table above reflects the last complete benchmark run using `qwen3-coder-plus-2025-07-22`. A subsequent attempt to re-run the full suite with `qwen3.7-max-2026-05-20` failed — that model returns `None` for Inspector/Sentinel structured-JSON prompts, making it incompatible with the multi-agent council. During that run the DashScope free quota was also exhausted, so the Semgrep+LLM condition degenerated to Semgrep-only. Final re-verification of the xss_app fix is pending a working model and available quota.

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
