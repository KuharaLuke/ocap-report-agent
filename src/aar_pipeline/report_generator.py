"""Sends a mission briefing to a local LLM and returns the generated report."""

from __future__ import annotations

from typing import ClassVar

from .llm_client import LLMClient
from .template_config import TemplateConfig


class ReportGenerator:
    """Calls an OpenAI-compatible chat completions endpoint (e.g. LM Studio)."""

    _seen_hashes: ClassVar[set[str]] = set()

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:1234",
        template: TemplateConfig | None = None,
    ) -> None:
        self._client = LLMClient(base_url)
        self._template = template or TemplateConfig.default()
        self._prefill = f"{self._template.unit_name}\n{self._template.unit_subline}\n"

    def generate(
        self,
        briefing: str,
        discord_context: str | None = None,
        temperature: float = 0.4,
    ) -> str:
        """Send briefing to the LLM and return the generated report text."""
        compact = self._template.content_hash in self._seen_hashes
        self._seen_hashes.add(self._template.content_hash)

        messages = self._build_messages(briefing, discord_context, compact=compact)
        result = self._client.chat(
            messages,
            temperature=temperature,
            extra_report_markers=[self._template.unit_name],
        )
        return self._prefill + result

    def _build_system_prompt(self, compact: bool = False) -> str:
        """Build the system prompt from the template config."""
        t = self._template

        # Section instructions
        if compact:
            sections_text = "Follow these sections: " + " | ".join(
                f"{s.number}. {s.title}" for s in t.sections
            )
        else:
            section_lines = []
            for s in t.sections:
                section_lines.append(f"{s.number}. {s.title}")
                if s.description:
                    section_lines.append(f"   {s.description}")
                section_lines.append("")
            sections_text = "\n".join(section_lines)

        # Signature instruction
        sig_text = "\n".join(t.signature_lines) if t.signature_lines else "[NAME]\n[Rank, Title]"

        return (
            f"You are a military intelligence officer for {t.unit_name}. "
            f"Write an After Action Report that STRICTLY follows the unit's AAR template format.\n\n"
            f"The report MUST begin with this exact header block (fill in the bracketed fields "
            f"from the briefing data):\n\n"
            f"{t.unit_name}\n"
            f"{t.unit_subline}\n"
            f"OPERATION [operation name derived from mission name] - AFTER ACTION REPORT\n"
            f"[Location / Map name]\n"
            f"[Date]\n"
            f"MEMORANDUM FOR\n\n"
            f"TO:                {t.to_field}\n"
            f"FROM:              {t.from_field}\n"
            f"SUBJECT:           {t.subject_field}\n"
            f"REF:               {t.ref_field}\n\n"
            f"Then write the following numbered sections:\n\n"
            f"{sections_text}\n"
            f"End the report with a signature block:\n"
            f"[Blank line]\n"
            f"{sig_text}\n\n"
            f"CRITICAL FORMATTING RULES:\n"
            f"- Follow the template structure EXACTLY. Do not skip or reorder sections.\n"
            f"- The header block ({t.unit_name} lines, OPERATION line, location, date, MEMORANDUM, "
            f"TO/FROM/SUBJECT/REF) is MANDATORY.\n"
            f"- The signature block at the end is MANDATORY.\n"
            f"- Write in formal military prose, third person.\n"
            f"- Use military time references. Use grid references when describing locations.\n"
            f"- Do not invent facts not present in the briefing data.\n"
            f"- Keep the total report under 1000 words.\n"
            f"- Output ONLY the finished report. No outlines, planning notes, drafts, or reasoning.\n"
            f"- Write complete prose paragraphs for each section.\n"
            f"- Start your response with: {t.unit_name}"
        )

    def _build_messages(
        self,
        briefing: str,
        discord_context: str | None = None,
        compact: bool = False,
    ) -> list[dict]:
        t = self._template
        user_content = (
            "Generate a complete After Action Report in formal prose from "
            "the following mission briefing data. Write the full document, "
            "not an outline.\n\n"
            f"IMPORTANT: You MUST output the complete header block BEFORE section 1. "
            f"After the two {t.unit_name} lines, output:\n"
            f"- OPERATION [name] - AFTER ACTION REPORT\n"
            f"- [Location]\n"
            f"- [Date]\n"
            f"- MEMORANDUM FOR\n"
            f"- TO: / FROM: / SUBJECT: / REF: fields\n"
            f"Do NOT skip straight to section 1.\n\n" + briefing
        )
        if discord_context:
            user_content += (
                "\n\n=== ADDITIONAL CONTEXT: PRE-MISSION PLANNING ===\n"
                "The following intelligence was extracted from the unit's "
                "pre-mission planning discussion. Use it to inform sections "
                "1 (Introduction), 2 (Summary), 6 (Intelligence Assessment), "
                "7 (Analysis), and 8 (Conclusion):\n\n"
                + discord_context
            )
        return [
            {"role": "system", "content": self._build_system_prompt(compact)},
            {"role": "user", "content": user_content},
            {"role": "assistant", "content": self._prefill},
        ]
