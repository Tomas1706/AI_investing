"""OpenAI ChatGPT integration for memo generation.

This module provides a thin wrapper around the Chat Completions API
to generate a conservative value-investing memo from a provided
evidence bundle. It is optional and fails gracefully if the API key
is missing or the request fails.
"""

from __future__ import annotations

import json
import os
from typing import Dict, Any, Optional


def _build_prompt(evidence: Dict[str, Any]) -> str:
    """Create a concise system+user prompt that enforces constraints."""
    instruction = (
        "You are a conservative, long-term value investor. Write a sober memo "
        "using ONLY the provided evidence. Do not invent numbers. Highlight "
        "uncertainty and risks. Keep it factual and cautious."
    )
    # Keep evidence compact; it's already structured. We'll include key parts.
    payload = json.dumps(evidence, ensure_ascii=False)
    return f"{instruction}\n\nEvidence (JSON):\n{payload}"


def generate_memo(
    *,
    evidence: Dict[str, Any],
    api_key: Optional[str],
    model: str = "gpt-4o-mini",
    temperature: float = 0.2,
    timeout: int = 60,
) -> Optional[str]:
    """Call OpenAI Chat Completions API to produce a memo text.

    Returns the memo text, or None on failure/missing key.
    """
    if not api_key:
        return None
    try:
        import requests  # type: ignore
    except Exception:
        return None

    url = "https://api.openai.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    data = {
        "model": model,
        "temperature": temperature,
        "messages": [
            {"role": "system", "content": "You are an expert value investor."},
            {
                "role": "user",
                "content": _build_prompt(evidence),
            },
        ],
    }
    try:
        r = requests.post(url, headers=headers, json=data, timeout=timeout)
        r.raise_for_status()
        js = r.json()
        msg = js.get("choices", [{}])[0].get("message", {}).get("content")
        if msg:
            return str(msg).strip()
    except Exception:
        return None
    return None
