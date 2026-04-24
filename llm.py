"""
app/adapters/llm.py — thin wrapper around LLM providers.

Supports:
  anthropic  — Claude (default)
  openai     — GPT-4o, etc.
  mock       — returns a canned string; used in tests

Swap providers without touching service logic.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

import httpx

from app.config import settings


class BaseLLMAdapter(ABC):
    @property
    @abstractmethod
    def model_name(self) -> str: ...

    @abstractmethod
    async def complete(self, system: str, user: str) -> str: ...


# ---------------------------------------------------------------------------
# Anthropic (Claude)
# ---------------------------------------------------------------------------

class AnthropicAdapter(BaseLLMAdapter):
    API_URL = "https://api.anthropic.com/v1/messages"
    API_VERSION = "2023-06-01"

    @property
    def model_name(self) -> str:
        return settings.llm_model

    async def complete(self, system: str, user: str) -> str:
        headers = {
            "x-api-key": settings.anthropic_api_key,
            "anthropic-version": self.API_VERSION,
            "content-type": "application/json",
        }
        body = {
            "model": self.model_name,
            "max_tokens": settings.llm_max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(self.API_URL, headers=headers, json=body)
            resp.raise_for_status()
            data = resp.json()
            return data["content"][0]["text"]


# ---------------------------------------------------------------------------
# OpenAI
# ---------------------------------------------------------------------------

class OpenAIAdapter(BaseLLMAdapter):
    API_URL = "https://api.openai.com/v1/chat/completions"

    @property
    def model_name(self) -> str:
        return settings.llm_model

    async def complete(self, system: str, user: str) -> str:
        headers = {
            "Authorization": f"Bearer {settings.openai_api_key}",
            "Content-Type": "application/json",
        }
        body = {
            "model": self.model_name,
            "max_tokens": settings.llm_max_tokens,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(self.API_URL, headers=headers, json=body)
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]


# ---------------------------------------------------------------------------
# Mock
# ---------------------------------------------------------------------------

class MockLLMAdapter(BaseLLMAdapter):
    @property
    def model_name(self) -> str:
        return "mock"

    async def complete(self, system: str, user: str) -> str:  # noqa: ARG002
        return (
            "[Mock reflection] This is a placeholder response. "
            "Set LLM_PROVIDER=anthropic and supply ANTHROPIC_API_KEY to get real output."
        )


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def get_llm_adapter() -> BaseLLMAdapter:
    provider = settings.llm_provider
    if provider == "anthropic":
        return AnthropicAdapter()
    if provider == "openai":
        return OpenAIAdapter()
    return MockLLMAdapter()
