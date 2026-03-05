"""LLM client abstraction for the judge agent.

Supports Groq and SiliconFlow (OpenAI-compatible APIs) so the judge
can use either provider for per-task and overall verdict calls.
"""
from __future__ import annotations

import asyncio

from openai import OpenAI

from app.config import (
    GROQ_API_KEY,
    GROQ_BASE_URL,
    GROQ_JUDGE_MODEL,
    JUDGE_PROVIDER,
    SILICONFLOW_API_KEY,
    SILICONFLOW_BASE_URL,
    SILICONFLOW_JUDGE_MODEL,
)


async def judge_llm_completion(
    system_prompt: str,
    user_content: str,
    response_format: dict | None = None,
) -> str:
    """Call the configured judge LLM provider and return the assistant message.

    Args:
        system_prompt: System message content.
        user_content: User message content.
        response_format: Optional dict for structured output, e.g.
            {"type": "json_object"} when supported by the model.

    Returns:
        The assistant message text.

    Raises:
        RuntimeError: If provider is not configured or API key is missing.
    """
    provider = JUDGE_PROVIDER
    if provider not in ("groq", "siliconflow"):
        raise RuntimeError(
            f"JUDGE_PROVIDER must be 'groq' or 'siliconflow', got '{provider}'."
        )

    if provider == "groq":
        if not GROQ_API_KEY:
            raise RuntimeError("GROQ_API_KEY is required when JUDGE_PROVIDER=groq.")
        client = OpenAI(api_key=GROQ_API_KEY, base_url=GROQ_BASE_URL)
        model = GROQ_JUDGE_MODEL
    else:  # siliconflow
        if not SILICONFLOW_API_KEY:
            raise RuntimeError(
                "SILICONFLOW_API_KEY is required when JUDGE_PROVIDER=siliconflow."
            )
        client = OpenAI(
            api_key=SILICONFLOW_API_KEY, base_url=SILICONFLOW_BASE_URL
        )
        model = SILICONFLOW_JUDGE_MODEL

    def _call() -> str:
        kwargs: dict = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
        }
        if response_format is not None:
            kwargs["response_format"] = response_format
        completion = client.chat.completions.create(**kwargs)
        text = completion.choices[0].message.content
        return text or ""

    return await asyncio.to_thread(_call)
