"""Thin wrapper around an OpenAI-compatible chat completions endpoint."""

from __future__ import annotations

import re

import requests


class LLMClient:
    """Shared LLM client for all components that need local model access."""

    def __init__(self, base_url: str = "http://127.0.0.1:1234") -> None:
        self.url = f"{base_url.rstrip('/')}/v1/chat/completions"

    def chat(
        self,
        messages: list[dict],
        model: str = "qwen/qwen3.5-9b",
        temperature: float = 0.4,
        max_tokens: int = 8192,
        timeout: int = 180,
    ) -> str:
        """Send a chat completion request and return the content string.

        Handles connection errors, timeouts, HTTP errors, and strips
        <think>...</think> blocks from Qwen CoT output.
        """
        payload = {
            "model": model,
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
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError):
            raise RuntimeError(f"Unexpected API response format: {data}")
        return self.strip_thinking(content)

    @staticmethod
    def strip_thinking(text: str) -> str:
        """Remove reasoning/thinking traces from models like Qwen that emit CoT."""
        # Strip <think>...</think> blocks
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
        # Strip orphaned </think> tags (when <think> was in prefill)
        if "</think>" in text:
            text = text.split("</think>")[-1].strip()

        # Detect and strip untagged CoT (analysis steps before the report)
        report_markers = [
            "TASK FORCE 405",
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
        for marker in report_markers:
            idx = text.find(marker)
            if idx > 0:
                return text[idx:].strip()

        return text.strip()
