"""Sends a mission briefing to a local LLM and returns the generated report."""

from __future__ import annotations

from llm_client import LLMClient


class ReportGenerator:
    """Calls an OpenAI-compatible chat completions endpoint (e.g. LM Studio)."""

    SYSTEM_PROMPT = (
        "You are a military intelligence officer for Task Force 405, SWTG - F Squadron. "
        "Write an After Action Report that STRICTLY follows the TF405 AAR template format.\n\n"
        "The report MUST begin with this exact header block (fill in the bracketed fields "
        "from the briefing data):\n\n"
        "TASK FORCE 405\n"
        "TASK FORCE 405 - SWTG - F SQUADRON\n"
        "OPERATION [operation name derived from mission name] - AFTER ACTION REPORT\n"
        "[Location / Map name]\n"
        "[Date]\n"
        "MEMORANDUM FOR\n\n"
        "TO:                CENTCOM\n"
        "FROM:              OIC, F SQUADRON\n"
        "SUBJECT:           After Action Report [Operation Name]\n"
        "REF:               NIL\n\n"
        "Then write the following 8 numbered sections:\n\n"
        "1. GENERAL INFORMATION / INTRODUCTION\n"
        "   Describe the commander's mission and intent.\n\n"
        "2. SUMMARY\n"
        "   The following is information regarding the contingency itself:\n"
        "   * Deployed Location: [location]\n"
        "   * Deployed Personnel: [list names and roles]\n"
        "   * Duration of Deployment: [start to end]\n"
        "   * Contingency Purpose: In support of [purpose]\n"
        "   * Scope of Operation: [scope]\n\n"
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
        "   Accuracy of Pre-Mission Intelligence: [If pre-mission planning context was "
        "provided, assess how accurately it predicted actual enemy disposition and "
        "operational conditions. If no pre-mission intel was provided, state N/A.]\n"
        "   New Intelligence Gathered During The Operation: [any new intel from "
        "the operation, e.g. enemy locations, composition, patterns]\n\n"
        "7. ANALYSIS AND RECOMMENDATIONS\n"
        "   SUSTAINMENT: Successful tactics, techniques, and procedures.\n"
        "   IMPROVEMENT: Challenges and actionable recommendations. "
        "Reference terrain considerations for future operations in similar AOs.\n\n"
        "8. CONCLUSION\n"
        "   Mission outcome summary.\n\n"
        "End the report with a signature block:\n"
        "[Blank line]\n"
        "[Commander name or 'OIC, F SQUADRON']\n"
        "[COMMANDER NAME IN ALL CAPS]\n"
        "[Rank, Title]\n\n"
        "CRITICAL FORMATTING RULES:\n"
        "- Follow the template structure EXACTLY. Do not skip or reorder sections.\n"
        "- The header block (TF405 lines, OPERATION line, location, date, MEMORANDUM, "
        "TO/FROM/SUBJECT/REF) is MANDATORY.\n"
        "- The signature block at the end is MANDATORY.\n"
        "- Write in formal military prose, third person.\n"
        "- Use military time references. Use grid references when describing locations.\n"
        "- Do not invent facts not present in the briefing data.\n"
        "- Keep the total report under 1000 words.\n"
        "- Output ONLY the finished report. No outlines, planning notes, drafts, or reasoning.\n"
        "- Write complete prose paragraphs for each section.\n"
        "- Start your response with: TASK FORCE 405"
    )

    def __init__(self, base_url: str = "http://127.0.0.1:1234") -> None:
        self._client = LLMClient(base_url)

    ASSISTANT_PREFILL = "TASK FORCE 405\nTASK FORCE 405 - SWTG - F SQUADRON\n"

    def generate(
        self,
        briefing: str,
        discord_context: str | None = None,
        temperature: float = 0.4,
    ) -> str:
        """Send briefing to the LLM and return the generated report text."""
        messages = self._build_messages(briefing, discord_context)
        result = self._client.chat(messages, temperature=temperature)
        # The LLM response continues after the prefill, so prepend it
        # to reconstruct the full report with the header block
        return self.ASSISTANT_PREFILL + result

    def _build_messages(
        self, briefing: str, discord_context: str | None = None
    ) -> list[dict]:
        user_content = (
            "Generate a complete After Action Report in formal prose from "
            "the following mission briefing data. Write the full document, "
            "not an outline.\n\n"
            "IMPORTANT: You MUST output the complete header block BEFORE section 1. "
            "After the two TASK FORCE 405 lines, output:\n"
            "- OPERATION [name] - AFTER ACTION REPORT\n"
            "- [Location]\n"
            "- [Date]\n"
            "- MEMORANDUM FOR\n"
            "- TO: / FROM: / SUBJECT: / REF: fields\n"
            "Do NOT skip straight to section 1.\n\n" + briefing
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
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
            {
                "role": "assistant",
                "content": self.ASSISTANT_PREFILL,
            },
        ]
