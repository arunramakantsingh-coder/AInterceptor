"""Fake provider — deterministic chunks for tests and UI wiring."""
from __future__ import annotations
import asyncio
from .base import Chunk


class FakeProvider:
    name = "fake"
    subsystem = "Interceptor"

    def __init__(self, reply: str = "hello from fake provider"):
        self.reply = reply
        self.authed = False

    async def authenticate(self) -> None:
        await asyncio.sleep(0)
        self.authed = True

    async def send_prompt(self, messages: list[dict]):
        if not self.authed:
            raise RuntimeError("not authenticated")
        for i, word in enumerate(self.reply.split(" ")):
            await asyncio.sleep(0)
            yield Chunk(provider=self.name, delta=word + (" " if i < self.reply.count(" ") else ""))
        yield Chunk(provider=self.name, delta="", finish_reason="stop")

    def supports_tools(self) -> bool:
        return False

    def get_model_mapping(self) -> dict:
        return {"fake-default": "fake"}
