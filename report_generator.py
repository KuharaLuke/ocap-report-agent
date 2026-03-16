"""Sends a mission briefing to a local LLM and returns the generated report."""

from __future__ import annotations

import re

import requests


class ReportGenerator:
    """Calls an OpenAI-compatible chat completions endpoint (e.g. LM Studio)."""

    SYSTEM_PROMPT = (
        "You are a military intelligence officer for Task Force 405, SWTG - F Squadron. "
        "Write an After Action Report following this exact structure:\n\n"
        "1. GENERAL INFORMATION / INTRODUCTION\n"
        "   Describe the commander's mission and intent.\n\n"
        "2. SUMMARY\n"
        "   * Deployed Location\n"
        "   * Deployed Personnel (list names and ranks)\n"
        "   * Duration of Deployment\n"
        "   * Contingency Purpose\n"
        "   * Scope of Operation\n\n"
        "3. NARRATIVE SUMMARY OF EXECUTION\n"
        "   Chronological timeline of all key actions from mission start to end. "
        "Include insertion, movement, enemy contact, and extraction. "
        "Reference grid coordinates and terrain conditions when describing engagements. "
        "Explain how terrain features (valleys, ridgelines, open ground, urban areas) "
        "influenced tactical outcomes, movement, and casualty patterns. "
        "Detail all critical decisions made by leadership.\n\n"
        "4. FRIENDLY FORCES ASSESSMENT\n"
        "   PERSONNEL: List all friendly casualties (KIA, WIA, MIA).\n"
        "   EQUIPMENT: Status of mission-critical equipment.\n"
        "   LOGISTICS: Ammunition and key supplies expended.\n\n"
        "5. ENEMY FORCES ASSESSMENT\n"
        "   COMPOSITION: Identify enemy forces encountered.\n"
        "   STRENGTH: Estimated number of enemy combatants engaged.\n"
        "   EQUIPMENT: Observed enemy weaponry, vehicles, equipment.\n"
        "   CASUALTIES: Confirmed enemy KIA.\n\n"
        "6. INTELLIGENCE ASSESSMENT\n"
        "   N/A - No pre-mission intelligence data available.\n\n"
        "7. ANALYSIS AND RECOMMENDATIONS\n"
        "   SUSTAINMENT: Successful tactics, techniques, and procedures.\n"
        "   IMPROVEMENT: Challenges and actionable recommendations. "
        "Reference terrain considerations for future operations in similar AOs.\n\n"
        "8. CONCLUSION\n"
        "   Mission outcome summary.\n\n"
        "Write in formal military prose, third person. "
        "Use military time references. Use grid references when describing locations. "
        "Do not invent facts not present in the briefing data. "
        "Keep the total report under 1000 words. "
        "CRITICAL: Output ONLY the finished report as a polished document. "
        "Do NOT output outlines, bullet points, planning notes, drafts, or reasoning steps. "
        "Write complete prose paragraphs for each section. "
        "Start your response with: TASK FORCE 405"
    )

    def __init__(self, base_url: str = "http://127.0.0.1:1234") -> None:
        self.url = f"{base_url.rstrip('/')}/v1/chat/completions"

    def generate(self, briefing: str, temperature: float = 0.4) -> str:
        """Send briefing to the LLM and return the generated report text."""
        messages = self._build_messages(briefing)
        payload = {
            "model": "qwen/qwen3.5-9b",
            "messages": messages,
            "temperature": temperature,
            "max_tokens": 8192,
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

    def _build_messages(self, briefing: str) -> list[dict]:
        return [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    "Generate a complete After Action Report in formal prose from "
                    "the following mission briefing data. Write the full document, "
                    "not an outline.\n\n" + briefing
                ),
            },
            {
                "role": "assistant",
                "content": "TASK FORCE 405\nTASK FORCE 405 - SWTG - F SQUADRON\n",
            },
        ]
