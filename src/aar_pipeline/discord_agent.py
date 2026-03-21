"""Fetches Discord thread messages and extracts structured pre-mission intelligence."""

from __future__ import annotations

import time
from datetime import datetime, timezone

import requests

from .llm_client import LLMClient


class DiscordAgent:
    """Retrieves Discord thread messages closest to a mission date
    and uses a local LLM to extract structured pre-mission intelligence."""

    DISCORD_API = "https://discord.com/api/v10"
    DISCORD_EPOCH = 1420070400000  # ms offset for Discord Snowflake IDs

    SUMMARIZE_PROMPT = (
        "You are a military intelligence analyst. Given a Discord thread containing "
        "pre-mission planning discussion for an Arma 3 operation, extract the following "
        "structured intelligence:\n\n"
        "1. COMMANDER'S INTENT: The stated mission objective and desired end state.\n"
        "2. PRE-MISSION INTELLIGENCE: Any intelligence briefings, enemy locations, "
        "force compositions, or terrain assessments shared before the mission.\n"
        "3. STRATEGIC CONTEXT: Background situation, political context, or ongoing "
        "campaign information that frames this operation.\n"
        "4. FORCE ORGANIZATION: How the team planned to organize (element assignments, "
        "roles, vehicle allocations).\n\n"
        "If a section has no relevant information, write 'None provided.'\n"
        "Write in formal military style. Be concise. "
        "Do not invent information not present in the messages."
    )

    MAX_THREAD_CHARS = 45000  # ~12K tokens, leaves room for system prompt + output

    def __init__(
        self,
        bot_token: str,
        channel_id: str,
        guild_id: str,
        llm_client: LLMClient,
    ) -> None:
        self._token = bot_token
        self._channel_id = channel_id
        self._guild_id = guild_id
        self._llm = llm_client
        self._session = requests.Session()
        self._session.headers.update({
            "Authorization": f"Bot {bot_token}",
        })

    def fetch_context(self, mission_date_utc: str) -> str | None:
        """Main entry point. Returns structured intel text or None on failure.

        Args:
            mission_date_utc: ISO 8601 datetime string from the OCAP2 mission.
        """
        try:
            mission_dt = datetime.fromisoformat(mission_date_utc)
            if mission_dt.tzinfo is None:
                mission_dt = mission_dt.replace(tzinfo=timezone.utc)

            threads = self._fetch_all_threads()
            if not threads:
                print("  No threads found in channel")
                return None

            thread = self._find_closest_thread(threads, mission_dt)
            if not thread:
                print("  No matching Discord thread found")
                return None

            thread_name = thread.get("name", "unnamed")
            print(f"  Matched thread: '{thread_name}' (id={thread['id']})")

            messages = self._fetch_all_messages(thread["id"])
            if not messages:
                print("  Thread has no messages")
                return None

            print(f"  Fetched {len(messages)} messages, summarizing...")
            return self._summarize_thread(messages)
        except Exception as e:
            print(f"  Discord agent error: {e}")
            return None

    # ------------------------------------------------------------------
    # Discord API methods
    # ------------------------------------------------------------------

    def _fetch_all_threads(self) -> list[dict]:
        """Fetch both active and archived threads from the channel."""
        threads = []

        # Active threads (guild-level endpoint, filter by parent)
        try:
            resp = self._api_get(f"/guilds/{self._guild_id}/threads/active")
            if resp:
                for t in resp.get("threads", []):
                    if t.get("parent_id") == self._channel_id:
                        threads.append(t)
        except requests.HTTPError as e:
            print(f"  Warning: failed to fetch active threads: {e}")

        # Archived threads (channel-level, paginated)
        before = None
        while True:
            params: dict = {"limit": 100}
            if before:
                params["before"] = before
            try:
                resp = self._api_get(
                    f"/channels/{self._channel_id}/threads/archived/public",
                    params=params,
                )
            except requests.HTTPError as e:
                print(f"  Warning: failed to fetch archived threads: {e}")
                break

            if not resp:
                break
            batch = resp.get("threads", [])
            threads.extend(batch)

            if not resp.get("has_more", False) or not batch:
                break
            # Paginate using the last thread's archive_timestamp
            last_meta = batch[-1].get("thread_metadata", {})
            before = last_meta.get("archive_timestamp")
            if not before:
                break
            time.sleep(0.5)

        return threads

    def _fetch_all_messages(self, thread_id: str) -> list[dict]:
        """Fetch all messages from a thread, handling pagination."""
        messages: list[dict] = []
        before = None
        while True:
            params: dict = {"limit": 100}
            if before:
                params["before"] = before
            try:
                batch = self._api_get(
                    f"/channels/{thread_id}/messages", params=params
                )
            except requests.HTTPError as e:
                print(f"  Warning: failed to fetch messages: {e}")
                break

            if not batch:
                break
            messages.extend(batch)
            before = batch[-1]["id"]  # oldest in this batch
            if len(batch) < 100:
                break
            time.sleep(0.5)

        messages.reverse()  # chronological order
        return messages

    def _api_get(self, path: str, params: dict | None = None) -> dict | list | None:
        """Make a GET request to the Discord API with rate limit handling."""
        url = f"{self.DISCORD_API}{path}"
        for attempt in range(3):
            resp = self._session.get(url, params=params, timeout=30)
            if resp.status_code == 429:
                retry_after = resp.json().get("retry_after", 1.0)
                time.sleep(retry_after)
                continue
            resp.raise_for_status()
            return resp.json()
        return None

    # ------------------------------------------------------------------
    # Thread matching
    # ------------------------------------------------------------------

    def _find_closest_thread(
        self, threads: list[dict], mission_date: datetime
    ) -> dict | None:
        """Find the thread whose creation time is closest to mission_date."""
        if not threads:
            return None

        best_thread = None
        best_delta = None

        for thread in threads:
            thread_dt = self._snowflake_to_datetime(thread["id"])
            delta = abs((thread_dt - mission_date).total_seconds())
            if best_delta is None or delta < best_delta:
                best_delta = delta
                best_thread = thread

        return best_thread

    @classmethod
    def _snowflake_to_datetime(cls, snowflake: str) -> datetime:
        """Convert a Discord Snowflake ID to a UTC datetime."""
        timestamp_ms = (int(snowflake) >> 22) + cls.DISCORD_EPOCH
        return datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)

    # ------------------------------------------------------------------
    # LLM summarization
    # ------------------------------------------------------------------

    def _summarize_thread(self, messages: list[dict]) -> str:
        """Use LLM to extract structured intel from Discord messages."""
        formatted = []
        for msg in messages:
            author = msg.get("author", {}).get("username", "Unknown")
            content = msg.get("content", "").strip()
            # Include embed descriptions
            for embed in msg.get("embeds", []):
                desc = embed.get("description", "")
                if desc:
                    content += f"\n[Embed: {desc}]"
            if not content:
                continue
            timestamp = msg.get("timestamp", "")[:19]
            formatted.append(f"[{author}] ({timestamp}): {content}")

        thread_text = "\n".join(formatted)
        # Truncate keeping newest messages (most relevant planning discussion)
        if len(thread_text) > self.MAX_THREAD_CHARS:
            thread_text = (
                "...[earlier messages truncated]...\n"
                + thread_text[-self.MAX_THREAD_CHARS :]
            )

        llm_messages = [
            {"role": "system", "content": self.SUMMARIZE_PROMPT},
            {"role": "user", "content": f"Discord thread messages:\n\n{thread_text}"},
        ]
        raw = self._llm.chat(
            llm_messages,
            temperature=0.3,
            max_tokens=2048,
        )
        return self._strip_reasoning(raw)

    @staticmethod
    def _strip_reasoning(text: str) -> str:
        """Strip untagged chain-of-thought reasoning before the structured output.

        Qwen sometimes emits 'Thinking Process:' or numbered analysis steps
        before the actual structured extraction. Find the first section header
        and discard everything before it.
        """
        markers = [
            "1. COMMANDER'S INTENT",
            "**1. COMMANDER'S INTENT",
            "COMMANDER'S INTENT:",
            "**COMMANDER'S INTENT",
        ]
        for marker in markers:
            idx = text.find(marker)
            if idx > 0:
                return text[idx:]
        return text
