"""Thin wrapper around OpenAI-compatible and Anthropic chat completions endpoints."""

from __future__ import annotations

import os
import re

import requests


class LLMClient:
    """Shared LLM client supporting OpenAI-compatible (LM Studio) and Anthropic backends.

    Provider is selected via the ``provider`` constructor argument:
    - ``"auto"`` (default): uses Anthropic if ``ANTHROPIC_API_KEY`` is set, else OpenAI.
    - ``"openai"``: always use OpenAI-compatible endpoint (LM Studio).
    - ``"anthropic"``: always use the Anthropic Messages API.
    """

    ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
    DEFAULT_OPENAI_MODEL = "qwen/qwen3.5-9b"
    DEFAULT_ANTHROPIC_MODEL = "claude-haiku-4-5-20251001"

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:1234",
        provider: str = "auto",
        api_key: str | None = None,
    ) -> None:
        if provider == "auto":
            provider = "anthropic" if os.environ.get("ANTHROPIC_API_KEY") else "openai"
        self.provider = provider

        if provider == "anthropic":
            self.url = self.ANTHROPIC_URL
            key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
            self._headers: dict[str, str] = {
                "x-api-key": key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            }
        else:
            self.url = f"{base_url.rstrip('/')}/v1/chat/completions"
            self._headers = {}

    def chat(
        self,
        messages: list[dict],
        model: str | None = None,
        temperature: float = 0.4,
        max_tokens: int = 8192,
        timeout: int = 180,
        extra_report_markers: list[str] | None = None,
    ) -> str:
        """Send a chat completion request and return the content string."""
        if self.provider == "anthropic":
            raw = self._chat_anthropic(messages, model, temperature, max_tokens, timeout)
        else:
            raw = self._chat_openai(messages, model, temperature, max_tokens, timeout)
        return self.strip_thinking(raw, extra_markers=extra_report_markers)

    # ------------------------------------------------------------------
    # OpenAI backend
    # ------------------------------------------------------------------

    def _chat_openai(
        self,
        messages: list[dict],
        model: str | None,
        temperature: float,
        max_tokens: int,
        timeout: int,
    ) -> str:
        payload = {
            "model": model or self.DEFAULT_OPENAI_MODEL,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
            "chat_template_kwargs": {"enable_thinking": False},
        }
        try:
            resp = requests.post(self.url, json=payload, timeout=timeout)
            resp.raise_for_status()
        except requests.ConnectionError:
            raise ConnectionError(
                f"Cannot connect to LM Studio at {self.url}. "
                "Ensure LM Studio is running with a model loaded."
            )
        except requests.Timeout:
            raise TimeoutError(f"LLM request timed out after {timeout} seconds.")
        except requests.HTTPError:
            raise RuntimeError(f"LLM API error: {resp.status_code} - {resp.text}")

        data = resp.json()
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError):
            raise RuntimeError(f"Unexpected API response format: {data}")

    # ------------------------------------------------------------------
    # Anthropic backend
    # ------------------------------------------------------------------

    def _chat_anthropic(
        self,
        messages: list[dict],
        model: str | None,
        temperature: float,
        max_tokens: int,
        timeout: int,
    ) -> str:
        # Extract system message(s) — Anthropic takes them as a top-level field
        system_parts: list[str] = []
        user_messages: list[dict] = []
        for msg in messages:
            if msg.get("role") == "system":
                content = msg.get("content", "")
                if content:
                    system_parts.append(content)
            else:
                user_messages.append(msg)

        converted = self._convert_messages_for_anthropic(user_messages)

        payload: dict = {
            "model": model or self.DEFAULT_ANTHROPIC_MODEL,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": converted,
        }
        if system_parts:
            payload["system"] = "\n\n".join(system_parts)

        try:
            resp = requests.post(self.url, json=payload, headers=self._headers, timeout=timeout)
            resp.raise_for_status()
        except requests.ConnectionError:
            raise ConnectionError(
                f"Cannot connect to Anthropic API at {self.url}. "
                "Check your network connection."
            )
        except requests.Timeout:
            raise TimeoutError(f"Anthropic API request timed out after {timeout} seconds.")
        except requests.HTTPError:
            raise RuntimeError(f"Anthropic API error: {resp.status_code} - {resp.text}")

        data = resp.json()
        try:
            return data["content"][0]["text"]
        except (KeyError, IndexError):
            raise RuntimeError(f"Unexpected Anthropic API response format: {data}")

    @staticmethod
    def _convert_messages_for_anthropic(messages: list[dict]) -> list[dict]:
        """Convert OpenAI-format message content blocks to Anthropic format.

        Handles the image_url → image source conversion for vision calls.
        String content is left as-is.
        """
        result = []
        for msg in messages:
            content = msg.get("content")
            if not isinstance(content, list):
                result.append(msg)
                continue

            converted_blocks = []
            for block in content:
                if block.get("type") == "image_url":
                    url = block.get("image_url", {}).get("url", "")
                    # Parse data URI: "data:<media_type>;base64,<data>"
                    if url.startswith("data:") and ";base64," in url:
                        header, _, b64_data = url.partition(";base64,")
                        media_type = header[len("data:"):]
                    else:
                        # Non-data-URI: fall back to a placeholder text block
                        converted_blocks.append({"type": "text", "text": f"[Image URL: {url}]"})
                        continue
                    converted_blocks.append({
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": b64_data,
                        },
                    })
                else:
                    converted_blocks.append(block)

            result.append({**msg, "content": converted_blocks})
        return result

    # ------------------------------------------------------------------
    # Post-processing (shared)
    # ------------------------------------------------------------------

    @staticmethod
    def strip_thinking(
        text: str, extra_markers: list[str] | None = None
    ) -> str:
        """Remove reasoning/thinking traces from models like Qwen that emit CoT."""
        # Strip <think>...</think> blocks
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
        # Strip orphaned </think> tags (when <think> was in prefill)
        if "</think>" in text:
            text = text.split("</think>")[-1].strip()

        # Detect and strip untagged CoT (analysis steps before the report)
        report_markers = [
            "**AFTER ACTION",
            "# AFTER ACTION",
            "## AFTER ACTION",
            "**1. GENERAL INFORMATION",
            "# 1. GENERAL INFORMATION",
            "## 1. GENERAL INFORMATION",
            "1. GENERAL INFORMATION",
            "**GENERAL INFORMATION",
            "**EXECUTIVE SUMMARY",
            "**1. EXECUTIVE SUMMARY",
            "# EXECUTIVE SUMMARY",
            "EXECUTIVE SUMMARY",
        ]
        # Prepend unit-specific markers (highest priority)
        if extra_markers:
            report_markers = list(extra_markers) + report_markers

        for marker in report_markers:
            idx = text.find(marker)
            if idx > 0:
                return text[idx:].strip()

        return text.strip()
