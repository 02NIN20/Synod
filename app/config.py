"""App settings from env."""

import os
import sys
from dotenv import load_dotenv

load_dotenv()

DASHSCOPE_API_KEY = os.environ.get("DASHSCOPE_API_KEY")
QWEN_MODEL = os.environ.get("QWEN_MODEL", "qwen3.6-plus-2026-04-02")
QWEN_AGENT_MODEL = os.environ.get("QWEN_AGENT_MODEL", QWEN_MODEL)

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
GITHUB_WEBHOOK_SECRET = os.environ.get("GITHUB_WEBHOOK_SECRET", "")
GITHUB_MAX_FILES_PER_PR = int(os.environ.get("GITHUB_MAX_FILES_PER_PR", "10"))
GITHUB_MAX_FILE_LINES = int(os.environ.get("GITHUB_MAX_FILE_LINES", "500"))

if not DASHSCOPE_API_KEY:
    print(
        "ERROR: DASHSCOPE_API_KEY not set.\n"
        "Create a .env file in the project root with:\n"
        f"  DASHSCOPE_API_KEY=sk-...\n"
        f"  QWEN_MODEL={QWEN_MODEL}\n"
        f"  QWEN_AGENT_MODEL={QWEN_AGENT_MODEL}\n",
        file=sys.stderr,
    )
    sys.exit(1)
