"""App settings from env."""

import os
from dotenv import load_dotenv

load_dotenv()

DASHSCOPE_API_KEY = os.environ.get("DASHSCOPE_API_KEY")
QWEN_MODEL = os.environ.get("QWEN_MODEL", "qwen3-coder-plus-2025-07-22")
