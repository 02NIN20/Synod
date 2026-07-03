# Synod

Multi-agent code review council powered by Qwen LLM.

## Architecture

```
┌─────────────────────────────────────────────────┐
│                    FastAPI                        │
│  POST /api/v1/review                             │
└──────────┬──────────────────────────────────────┘
           │
┌──────────▼──────────────────────────────────────┐
│              CouncilOrchestrator                  │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐       │
│  │Cartographer│  │ Inspector │  │ Sentinel │       │
│  │ (structure)│  │ (quality) │  │(security)│       │
│  └─────┬────┘  └────┬─────┘  └────┬─────┘       │
│        │             │             │              │
│        └─────────────┴─────────────┘              │
│                        │                          │
│                 ┌──────▼──────┐                   │
│                 │   Arbiter    │                   │
│                 │ (dedup +    │                   │
│                 │  consensus) │                   │
│                 └─────────────┘                   │
│                                                   │
│  ┌─────────────────────────────────────────┐      │
│  │ Smith (fix loop, optional)               │      │
│  └─────────────────────────────────────────┘      │
└──────────────────────────────────────────────────┘
```

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
