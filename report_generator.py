"""Sends a mission briefing to a local LLM and returns the generated report."""

from __future__ import annotations

import re

import requests


class ReportGenerator:
    """Calls an OpenAI-compatible chat completions endpoint (e.g. LM Studio)."""

    SYSTEM_PROMPT = (
        "You are a military intelligence officer writing an After Action Report (AAR). "
        "Write in formal military prose, third person. Structure the report with these sections:\n\n"
        "1. EXECUTIVE SUMMARY (2-3 sentences)\n"
        "2. MISSION OVERVIEW (situation, task, purpose)\n"
        "3. CHRONOLOGICAL NARRATIVE (describe engagement phases in order, reference "
        "specific personnel by rank and name, mention weapons and distances for notable shots)\n"
        "4. PERSONNEL PERFORMANCE (brief assessment of each team member's contribution)\n"
        "5. EQUIPMENT NOTES (weapons effectiveness, vehicle encounters)\n"
        "6. LESSONS LEARNED (2-3 tactical observations)\n\n"
        "Use military time references. Refer to enemy forces as OPFOR or hostile combatants. "
        "Refer to friendly forces as the patrol element or by callsign Alpha 1-1. "
        "Do not invent facts not present in the briefing data. "
        "Keep the total report under 800 words. "
        "Output ONLY the report itself. Do not include any thinking, analysis, "
        "reasoning steps, or drafting notes. Start directly with the first section header."
    )

    def __init__(self, base_url: str = "http://127.0.0.1:1234") -> None:
        self.url = f"{base_url.rstrip('/')}/v1/chat/completions"

    def generate(self, briefing: str, temperature: float = 0.7) -> str:
        """Send briefing to the LLM and return the generated report text."""
        messages = self._build_messages(briefing)
        payload = {
            "model": "local-model",
            "messages": messages,
            "temperature": temperature,
            "max_tokens": 4096,
            "stream": False,
            "chat_template_kwargs": {"enable_thinking": False},
        }

        try:
            resp = requests.post(self.url, json=payload, timeout=180)
            resp.raise_for_status()
        except requests.ConnectionError:
            raise ConnectionError(
                f"Cannot connect to LM Studio at {self.url}. "
                "Ensure LM Studio is running with a model loaded."
            )
        except requests.Timeout:
            raise TimeoutError("LLM request timed out after 180 seconds.")
        except requests.HTTPError:
            raise RuntimeError(f"LLM API error: {resp.status_code} - {resp.text}")

        data = resp.json()
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError):
            raise RuntimeError(f"Unexpected API response format: {data}")
        return self._strip_thinking(content)

    @staticmethod
    def _strip_thinking(text: str) -> str:
        """Remove reasoning/thinking traces from models like Qwen that emit CoT."""
        # Strip <think>...</think> blocks
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()

        # Detect and strip untagged CoT (numbered analysis steps before the report)
        # Look for report markers that signal the actual AAR content
        report_markers = [
            "**AFTER ACTION",
            "# AFTER ACTION",
            "## AFTER ACTION",
            "**EXECUTIVE SUMMARY",
            "**1. EXECUTIVE SUMMARY",
            "# EXECUTIVE SUMMARY",
            "## 1. EXECUTIVE SUMMARY",
            "EXECUTIVE SUMMARY",
        ]
        for marker in report_markers:
            idx = text.find(marker)
            if idx > 0:
                return text[idx:].strip()

        return text.strip()

    def _build_messages(self, briefing: str) -> list[dict]:
        return [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    "Generate an After Action Report from the following "
                    "mission briefing data:\n\n" + briefing
                ),
            },
        ]
