"""
services/providers/llm.py
=========================
Pluggable LLM providers (NVIDIA, OpenAI, Anthropic, Ollama, etc.).
"""

from __future__ import annotations

import asyncio
from typing import AsyncIterator

from backend.services.interfaces.base import LLMInterface


class NVIDIALLMProvider(LLMInterface):
    def __init__(self, config: dict):
        from openai import OpenAI
        self.client = OpenAI(api_key=config["api_key"], base_url=config["base_url"])
        self._model = config.get("model", "meta/llama-3.1-70b-instruct")

    async def generate(self, messages: list[dict], temperature: float = 0.7, max_tokens: int = 1024) -> str:
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: self.client.chat.completions.create(
                model=self._model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            ),
        )
        return response.choices[0].message.content.strip()

    async def generate_stream(self, messages: list[dict], temperature: float = 0.7, max_tokens: int = 1024) -> AsyncIterator[str]:
        loop = asyncio.get_event_loop()

        def _create():
            return self.client.chat.completions.create(
                model=self._model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True,
            )

        stream = await loop.run_in_executor(None, _create)
        for chunk in stream:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    def model_name(self) -> str:
        return self._model

    async def health(self) -> dict:
        try:
            await self.generate([{"role": "user", "content": "ping"}], max_tokens=5)
            return {"status": "healthy", "provider": "nvidia", "model": self._model}
        except Exception as e:
            return {"status": "unhealthy", "provider": "nvidia", "error": str(e)}


class OpenAILLMProvider(LLMInterface):
    def __init__(self, config: dict):
        from openai import OpenAI
        self.client = OpenAI(api_key=config["api_key"])
        self._model = config.get("model", "gpt-4o")

    async def generate(self, messages: list[dict], temperature: float = 0.7, max_tokens: int = 1024) -> str:
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: self.client.chat.completions.create(
                model=self._model, messages=messages, temperature=temperature, max_tokens=max_tokens,
            ),
        )
        return response.choices[0].message.content.strip()

    async def generate_stream(self, messages: list[dict], temperature: float = 0.7, max_tokens: int = 1024) -> AsyncIterator[str]:
        loop = asyncio.get_event_loop()

        def _create():
            return self.client.chat.completions.create(
                model=self._model, messages=messages, temperature=temperature, max_tokens=max_tokens, stream=True,
            )

        stream = await loop.run_in_executor(None, _create)
        for chunk in stream:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    def model_name(self) -> str:
        return self._model

    async def health(self) -> dict:
        try:
            await self.generate([{"role": "user", "content": "ping"}], max_tokens=5)
            return {"status": "healthy", "provider": "openai", "model": self._model}
        except Exception as e:
            return {"status": "unhealthy", "provider": "openai", "error": str(e)}


class OllamaLLMProvider(LLMInterface):
    def __init__(self, config: dict):
        self._base_url = config.get("base_url", "http://ollama:11434")
        self._model = config.get("model", "llama3.1:70b")

    async def generate(self, messages: list[dict], temperature: float = 0.7, max_tokens: int = 1024) -> str:
        import httpx
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self._base_url}/api/chat",
                json={"model": self._model, "messages": messages, "stream": False, "options": {"temperature": temperature, "num_predict": max_tokens}},
                timeout=120,
            )
            resp.raise_for_status()
            return resp.json()["message"]["content"]

    async def generate_stream(self, messages: list[dict], temperature: float = 0.7, max_tokens: int = 1024) -> AsyncIterator[str]:
        import httpx
        async with httpx.AsyncClient() as client:
            async with client.stream(
                "POST",
                f"{self._base_url}/api/chat",
                json={"model": self._model, "messages": messages, "stream": True, "options": {"temperature": temperature, "num_predict": max_tokens}},
                timeout=120,
            ) as resp:
                async for line in resp.aiter_lines():
                    if line:
                        import json
                        data = json.loads(line)
                        if "message" in data:
                            yield data["message"].get("content", "")

    def model_name(self) -> str:
        return self._model

    async def health(self) -> dict:
        try:
            import httpx
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"{self._base_url}/api/tags", timeout=5)
                return {"status": "healthy", "provider": "ollama", "model": self._model}
        except Exception as e:
            return {"status": "unhealthy", "provider": "ollama", "error": str(e)}


def get_llm_provider(config: dict) -> LLMInterface:
    provider = config.get("provider", "nvidia")
    if provider == "nvidia":
        return NVIDIALLMProvider(config["nvidia"])
    elif provider == "openai":
        return OpenAILLMProvider(config["openai"])
    elif provider == "ollama":
        return OllamaLLMProvider(config.get("ollama", {"base_url": "http://ollama:11434"}))
    else:
        raise ValueError(f"Unsupported LLM provider: {provider}")
