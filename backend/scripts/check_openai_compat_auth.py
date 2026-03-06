#!/usr/bin/env python3
"""Check which OpenAI-compatible provider (Groq or SiliconFlow) has an auth issue.

Run from project root or backend:
  python backend/scripts/check_openai_compat_auth.py
  # or from backend:
  python scripts/check_openai_compat_auth.py
"""
import sys
from pathlib import Path

# Load backend .env
_backend = Path(__file__).resolve().parent.parent
if str(_backend) not in sys.path:
    sys.path.insert(0, str(_backend))

from dotenv import load_dotenv
load_dotenv(_backend / ".env")
load_dotenv()

from openai import OpenAI

def check(name: str, api_key: str, base_url: str | None, model: str) -> None:
    if not api_key:
        print(f"  {name}: SKIP (no API key set)")
        return
    try:
        client = OpenAI(api_key=api_key, base_url=base_url) if base_url else OpenAI(api_key=api_key)
        r = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "Say OK"}],
            max_tokens=5,
        )
        text = (r.choices[0].message.content or "").strip()
        print(f"  {name}: OK (response: {text!r})")
    except Exception as e:
        err = str(e).split("\n")[0]
        print(f"  {name}: FAIL — {err}")

if __name__ == "__main__":
    import os
    print("Checking OpenAI-compatible API auth (Groq / SiliconFlow)...")
    print()

    groq_key = os.getenv("GROQ_API_KEY", "")
    groq_base = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1")
    groq_model = os.getenv("GROQ_PLANNER_MODEL", "llama-3.1-8b-instant")
    print("Groq:")
    check("Groq", groq_key, groq_base, groq_model)
    print()

    sf_key = os.getenv("SILICONFLOW_API_KEY", "")
    sf_base = os.getenv("SILICONFLOW_BASE_URL", "https://api.siliconflow.cn/v1")
    sf_model = os.getenv("SILICONFLOW_JUDGE_MODEL", "Qwen/Qwen3-VL-30B-A3B-Thinking")
    print("SiliconFlow:")
    check("SiliconFlow", sf_key, sf_base, sf_model)
    print()
    print("Done. Any FAIL is likely an invalid/expired key or wrong base URL.")
