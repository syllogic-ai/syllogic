"""
Thin wrapper around the Anthropic Python SDK with cost calculation.
Centralizes model-id constants and exposes a function for parse-schedule
and a separate path for the full Claude Agent SDK invocation.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from anthropic import Anthropic

DEFAULT_MODEL = "claude-sonnet-4-6"

# USD per 1M tokens — keep these conservative; runs may price slightly under.
# https://docs.anthropic.com/en/docs/about-claude/pricing
_RATES = {
    "claude-sonnet-4-6": {"input": 3.0, "output": 15.0},
    "claude-opus-4-7":   {"input": 15.0, "output": 75.0},
    "claude-haiku-4-5":  {"input": 0.80, "output": 4.0},
}


@dataclass
class TokenUsage:
    input_tokens: int
    output_tokens: int

    def cost_cents(self, model: str) -> int:
        rate = _RATES.get(model, _RATES[DEFAULT_MODEL])
        usd = (self.input_tokens / 1_000_000) * rate["input"] + (self.output_tokens / 1_000_000) * rate["output"]
        return int(round(usd * 100))


def get_client() -> Anthropic:
    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not configured")
    return Anthropic(api_key=api_key)


def is_configured() -> bool:
    return bool(os.getenv("ANTHROPIC_API_KEY", "").strip())
