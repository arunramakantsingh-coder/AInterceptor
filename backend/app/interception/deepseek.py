from __future__ import annotations

import pathlib
import json
import os
import re
from pathlib import Path
from typing import Any

from app.interception.chrome_auth import ensure_chrome_cdp, existing_chrome_cdp
from app.interception.nonclaude_runtime import NonClaudeWebRuntime
from app.interception.web_runtime import WebProviderSpec


"""DeepSeek Web runtime using browser transport interception."""
from app.interception import registry as provider_registry
class DeepSeekStreamParser:
    """Stateful parser for DeepSeek Web's SSE patch protocol."""

    def __init__(self) -> None:
        self._path_buffers: dict[str, str] = {}
        self._pending = ""
        self._cumulative_body_seen = ""
        self._fragments: list[dict[str, Any]] = []
        self._active_path = ""
        self._active_op = ""
        self._message_id: str | None = None
        self._choice_text = ""

    @staticmethod
    def _text_values(value: Any) -> list[str]:
        if isinstance(value, str):
            return [value] if value else []
        if isinstance(value, list):
            out: list[str] = []
            for item in value:
                out.extend(DeepSeekStreamParser._text_values(item))
            return out
        if isinstance(value, dict):
            for key in ("text", "content"):
                if key in value:
                    return DeepSeekStreamParser._text_values(value[key])
        return []

    @staticmethod
    def _clone_fragment(fragment: Any) -> dict[str, Any]:
        return dict(fragment) if isinstance(fragment, dict) else {"type": "RESPONSE", "content": ""}

    @staticmethod
    def _merge_append(existing: str, incoming: str) -> str:
        """Apply an APPEND value literally; never guess overlap at character level."""
        if not incoming:
            return existing
        return existing + incoming

    @classmethod
    def _join_response_parts(cls, parts: list[str]) -> str:
        """Join fragments from a snapshot's `fragments` array.

        Never strips leading/trailing whitespace of any fragment: DeepSeek
        streams word boundaries as separate fragments ("sent ", "\"hi").
        Stripping any fragment corrupts those boundaries.
        """
        assembled = ""
        for part in parts:
            if part is None or part == "":
                continue
            if not assembled:
                assembled = part
                continue
            if part == assembled:
                continue
            if part.startswith(assembled):
                assembled = part
                continue
            if assembled.startswith(part):
                continue
            assembled = f"{assembled}\n\n{part}"
        return assembled

    @property
    def current(self) -> str:
        parts: list[str] = []
        for fragment in self._fragments:
            if str(fragment.get("type") or "").upper() == "RESPONSE":
                parts.extend(self._text_values(fragment.get("content")))
        if parts:
            return self._join_response_parts(parts)
        return self._choice_text

    def _resolve_index(self, raw: str) -> int | None:
        try:
            index = int(raw)
        except (TypeError, ValueError):
            return None
        if index < 0:
            index += len(self._fragments)
        return max(index, 0)

    def _ensure_fragment(self, index: int) -> dict[str, Any]:
        while len(self._fragments) <= index:
            self._fragments.append({"type": "RESPONSE", "content": ""})
        return self._fragments[index]

    def _append_content(self, fragment: dict[str, Any], value: Any) -> None:
        incoming = "".join(self._text_values(value))
        if not incoming:
            return
        existing = "".join(self._text_values(fragment.get("content")))
        # Idempotency: if the incoming text already appears at the end of the
        # fragment (replayed cumulative frame), do not duplicate it.
        if existing.endswith(incoming) and len(existing) >= len(incoming):
            return
        fragment["content"] = self._merge_append(existing, incoming)

    def _apply_patch(self, path: str, operation: str, value: Any) -> None:
        path = path.lstrip("/")
        op = (operation or "APPEND").upper()

        if op == "BATCH" and isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    self._apply_patch(str(item.get("p") or path), str(item.get("o") or "APPEND"), item.get("v"))
            return

        if path in {"response/fragments", "fragments"} and isinstance(value, list):
            if op in {"SET", "REPLACE"}:
                self._fragments = [self._clone_fragment(item) for item in value]
            elif op == "APPEND":
                self._fragments.extend(self._clone_fragment(item) for item in value)
            return

        match = re.match(r"^(?:response/)?fragments/(-?\d+)/content$", path)
        if match:
            index = self._resolve_index(match.group(1))
            if index is None:
                return
            fragment = self._ensure_fragment(index)
            if op in {"SET", "REPLACE"}:
                fragment["content"] = "".join(self._text_values(value))
            elif op in {"APPEND", ""}:
                # Literal append to the fragment's OWN current content.
                # Never consult a path-keyed buffer: the -1 index resolves
                # to a different fragment as new ones arrive, and mixing
                # across fragments loses the leading snapshot content.
                self._append_content(fragment, value)
            return

        match = re.match(r"^(?:response/)?fragments/(-?\d+)$", path)
        if match and isinstance(value, dict):
            index = self._resolve_index(match.group(1))
            if index is None:
                return
            if op in {"SET", "REPLACE"}:
                self._fragments[index] = self._clone_fragment(value)
            else:
                self._ensure_fragment(index).update(self._clone_fragment(value))

    def _extract_snapshot(self, obj: dict[str, Any]) -> bool:
        found = False
        containers = [obj]
        if isinstance(obj.get("v"), dict):
            containers.append(obj["v"])
        for container in containers:
            response = container.get("response")
            if not isinstance(response, dict):
                continue
            fragments = response.get("fragments")
            if isinstance(fragments, list):
                self._fragments = [self._clone_fragment(item) for item in fragments]
                found = True
            message_id = response.get("message_id") or response.get("response_message_id")
            if message_id:
                self._message_id = str(message_id)
            if found:
                return True
        return False

    def _extract_choices(self, obj: dict[str, Any]) -> None:
        choices = obj.get("choices")
        if not isinstance(choices, list):
            return
        for choice in choices:
            if not isinstance(choice, dict):
                continue
            delta = choice.get("delta")
            if isinstance(delta, dict):
                self._choice_text = self._merge_append(
                    self._choice_text,
                    "".join(self._text_values(delta.get("content") or delta.get("text"))),
                )
            message = choice.get("message")
            if isinstance(message, dict):
                self._choice_text = self._merge_append(
                    self._choice_text,
                    "".join(self._text_values(message.get("content"))),
                )

    def _feed_object(self, obj: Any) -> None:
        if not isinstance(obj, dict):
            return
        snapshot = self._extract_snapshot(obj)
        if "p" in obj:
            self._active_path = str(obj.get("p") or "")
        if "o" in obj:
            self._active_op = str(obj.get("o") or "").upper()
        if "v" in obj:
            if not (snapshot and isinstance(obj.get("v"), dict) and "response" in obj["v"]):
                if self._active_path:
                    self._apply_patch(self._active_path, self._active_op, obj.get("v"))
                elif isinstance(obj.get("v"), str) and self._fragments:
                    self._append_content(self._fragments[-1], obj.get("v"))
        self._extract_choices(obj)

    def _consume_line(self, line: str) -> None:
        raw = line.strip()
        if raw.startswith(")]}'"):
            raw = raw[4:].lstrip("\r\n ")
        if raw.startswith("data:"):
            raw = raw[5:].strip()
        if not raw or raw == "[DONE]":
            return
        try:
            self._feed_object(json.loads(raw))
        except json.JSONDecodeError:
            self._pending = raw

    def feed(self, chunk: str) -> str:
        if not isinstance(chunk, str) or not chunk:
            return self.current
        self._pending += chunk
        lines = self._pending.splitlines(keepends=True)
        self._pending = ""
        for line in lines:
            if line.endswith(("\n", "\r")):
                self._consume_line(line)
            else:
                self._pending = line

        if self._pending.strip():
            raw = self._pending.strip()
            candidate = raw[5:].strip() if raw.startswith("data:") else raw
            if candidate != "[DONE]":
                try:
                    obj = json.loads(candidate)
                except json.JSONDecodeError:
                    pass
                else:
                    self._pending = ""
                    self._feed_object(obj)
            else:
                self._pending = ""
        return self.current

    def __call__(self, cumulative_body: str) -> str:
        """Feed a growing cumulative body; never lose already-parsed state.

        If the new body starts with what we've seen: parse only the new suffix.
        If the body diverges (rare, provider rewrite): replay the ENTIRE body
        against a fresh parser, then adopt that as authoritative — the caller
        can diff old vs new at the string level.
        """
        if not isinstance(cumulative_body, str):
            return self.current
        if cumulative_body.startswith(self._cumulative_body_seen):
            suffix = cumulative_body[len(self._cumulative_body_seen):]
            self._cumulative_body_seen = cumulative_body
            return self.feed(suffix)

        # Diverged: full replay, keep old fragments as a fallback if replay yields less
        prior = self.current
        self.__init__()
        result = self.feed(cumulative_body)
        # Never return less content than we already had
        if len(result) < len(prior):
            return prior
        self._cumulative_body_seen = cumulative_body
        return result

    def finish(self) -> str:
        if self._pending and self._pending.strip():
            raw = self._pending.strip()
            if raw.startswith("data:"):
                raw = raw[5:].strip()
            if raw != "[DONE]":
                try:
                    self._feed_object(json.loads(raw))
                except json.JSONDecodeError:
                    pass
            self._pending = ""
        return self.current


def parse_deepseek_web(body: str) -> str:
    parser = DeepSeekStreamParser()
    parser.feed(body)
    return parser.finish()


class DeepSeekRuntime(NonClaudeWebRuntime):
    provider = "deepseek"

    def __init__(
        self,
        session_path: str | None = None,
        headless: bool = False,
        cdp_url: str | None = None,
    ) -> None:
        spec = WebProviderSpec(
            provider="deepseek",
            home_url="https://chat.deepseek.com/",
            login_markers=("/login", "/auth", "/sign_in", "/signin"),
            response_markers=("/api/v0/chat/completion",),
            request_markers=("/api/v0/chat/completion",),
            default_model="deepseek-flash",
            composer_selectors=(
                'textarea[placeholder*="Message"]',
                'textarea[placeholder*="message"]',
                "textarea",
                '[contenteditable="true"]',
                '[role="textbox"]',
            ),
        )
        # Resolve CDP ONLY through the registry; never fall back to the shared
        # "existing_chrome_cdp()" (which points at whichever browser is running
        # for Claude — a cross-provider leak that caused prompts to appear in
        # the wrong chat).
        explicit = cdp_url or os.getenv("AINTERCEPTOR_DEEPSEEK_CDP_URL")
        resolved = explicit if explicit is not None else provider_registry.cdp_url("deepseek")
        sp = (
            session_path
            or os.getenv("AINTERCEPTOR_DEEPSEEK_STORAGE_STATE")
            or str(pathlib.Path(".ainterceptor") / "deepseek" / "storage_state.json")
        )
        super().__init__(spec, session_path=sp, cdp_url=resolved,
                         headless=headless, parser=DeepSeekStreamParser())
