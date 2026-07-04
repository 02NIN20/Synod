"""App settings from env."""

import os
import sys
from dotenv import load_dotenv

load_dotenv()

DASHSCOPE_API_KEY = os.environ.get("DASHSCOPE_API_KEY")
QWEN_MODEL = os.environ.get("QWEN_MODEL", "qwen3-coder-plus-2025-07-22")

if not DASHSCOPE_API_KEY:
    print(
        "ERROR: DASHSCOPE_API_KEY not set.\n"
        "Create a .env file in the project root with:\n"
        f"  DASHSCOPE_API_KEY=sk-...\n"
        f"  QWEN_MODEL={QWEN_MODEL}\n",
        file=sys.stderr,
    )
    sys.exit(1)
