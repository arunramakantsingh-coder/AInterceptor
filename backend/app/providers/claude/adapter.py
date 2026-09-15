"""Claude provider — wraps ClaudeInterceptor into ProviderAdapter."""
from __future__ import annotations
from typing import AsyncIterator
from app.interception.claude import ClaudeInterceptor
from app.providers.base import Chunk


class ClaudeProvider:
    name = "claude"
    subsystem = "Interceptor"

    def __init__(self, session_path: str):
        self.session_path = session_path

    async def authenticate(self) -> None:
        return None

    async def send_prompt(self, messages: list[dict]) -> AsyncIterator[Chunk]:
        prompt = messages[-1]["content"] if messages else ""
        async with ClaudeInterceptor(self.session_path, headless=True) as ci:
            async for chunk in ci.stream(prompt):
                yield chunk

    def supports_tools(self) -> bool:
        return False

    def get_model_mapping(self) -> dict:
        return {"claude-web": "claude"}
