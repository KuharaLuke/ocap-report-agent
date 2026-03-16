"""Condenses a Mission object into a compact text briefing for LLM consumption."""

from __future__ import annotations

from collections import Counter

from models.entity import VehicleEntity
from models.event import KillEvent
from models.mission import Mission


class ReportBuilder:
    """Transforms parsed OCAP2 mission data into a structured briefing document.

    The output is designed to fit within ~1500 tokens so that a small LLM
    (e.g. Qwen 3.5 9B) can produce a coherent after-action report from it.
    """

    NUM_PHASES = 5

    def __init__(self, mission: Mission) -> None:
        self.mission = mission

    def build(self) -> str:
        sections = [
            self._mission_header(),
            self._player_roster(),
            self._timeline_phases(),
            self._notable_engagements(),
            self._enemy_composition(),
            self._vehicle_assets(),
            self._casualty_summary(),
        ]
        return "\n\n".join(sections)

    # ------------------------------------------------------------------
    # Section builders
    # ------------------------------------------------------------------

    def _mission_header(self) -> str:
        m = self.mission
        mins = int(m.duration_seconds // 60)
        secs = int(m.duration_seconds % 60)
        game_date = m.times[0].date if m.times else "unknown"
        real_date = m.times[0].system_time_utc.split("T")[0] if m.times else "unknown"
        return (
            "=== MISSION BRIEFING DATA ===\n"
            f"MISSION: {m.mission_name}\n"
            f"LOCATION: {m.world_name.title()}\n"
            f"DURATION: {mins}m {secs}s ({m.end_frame} frames @ {m.capture_delay}s/frame)\n"
            f"GAME DATE: {game_date}\n"
            f"REAL DATE: {real_date}"
        )

    def _player_roster(self) -> str:
        m = self.mission
        lines = ["FRIENDLY FORCES:"]
        for p in m.players:
            kills = len(m.kills_by(p.id))
            deaths = len(m.deaths_of(p.id))
            acc = (
                f"{p.total_shots and (len([h for h in m.hits if h.attacker_id == p.id]) / p.total_shots * 100):.0f}%"
                if p.total_shots > 0
                else "N/A"
            )
            status = self._player_status(p)
            lines.append(
                f"  {p.name:<22} | {p.role:<22} | {kills}K/{deaths}D | {acc} acc | {status}"
            )
        return "\n".join(lines)

    def _player_status(self, player) -> str:
        m = self.mission
        death_frame = player.death_frame
        if death_frame is None:
            return "Survived"
        ts = self._frame_to_timestamp(death_frame)
        later_kills = [k for k in m.kills_by(player.id) if k.frame > death_frame]
        if later_kills:
            return f"KIA {ts}, returned to action"
        # Check for self-kill
        deaths = m.deaths_of(player.id)
        for d in deaths:
            if d.attacker_id == player.id:
                return f"KIA {ts} (self-inflicted)"
        return f"KIA {ts}"

    def _timeline_phases(self) -> str:
        m = self.mission
        phase_size = max(1, m.end_frame // self.NUM_PHASES)
        kills = m.kills
        lines = ["TIMELINE:"]

        for i in range(self.NUM_PHASES):
            start = i * phase_size
            end = (i + 1) * phase_size if i < self.NUM_PHASES - 1 else m.end_frame
            phase_kills = [k for k in kills if start <= k.frame < end]
            if not phase_kills:
                lines.append(
                    f"  Phase {i+1} ({self._frame_to_timestamp(start)}-{self._frame_to_timestamp(end)}): "
                    f"No kills"
                )
                continue

            # Aggregate kills by attacker
            attacker_counts: Counter[str] = Counter()
            for k in phase_kills:
                att = m.get_entity(k.attacker_id)
                name = att.name if att else "Unknown"
                attacker_counts[name] += 1

            top_attackers = ", ".join(
                f"{name} ({cnt})" for name, cnt in attacker_counts.most_common(4)
            )

            # Player casualties in this phase
            player_deaths = []
            for k in phase_kills:
                victim = m.get_entity(k.victim_id)
                if victim and victim.is_player:
                    att = m.get_entity(k.attacker_id)
                    att_name = att.name if att else "Unknown"
                    weapon = self._shorten_weapon(k.weapon)
                    if k.attacker_id == k.victim_id:
                        player_deaths.append(f"** {victim.name} self-killed ({weapon})")
                    else:
                        player_deaths.append(
                            f"** {victim.name} KIA by {att_name} ({weapon}, {k.distance}m)"
                        )

            intensity = self._intensity_label(len(phase_kills))
            lines.append(
                f"  Phase {i+1} ({self._frame_to_timestamp(start)}-{self._frame_to_timestamp(end)}): "
                f"{len(phase_kills)} kills - {intensity}. {top_attackers}"
            )
            for pd in player_deaths:
                lines.append(f"    {pd}")

        return "\n".join(lines)

    def _notable_engagements(self) -> str:
        m = self.mission
        lines = ["NOTABLE ENGAGEMENTS:"]

        # Top 3 longest kills
        valid_kills = [k for k in m.kills if k.distance > 0]
        longest = sorted(valid_kills, key=lambda k: k.distance, reverse=True)[:3]
        for k in longest:
            att = m.get_entity(k.attacker_id)
            vic = m.get_entity(k.victim_id)
            lines.append(
                f"  {att.name if att else '?'} killed {vic.name if vic else '?'} "
                f"at {k.distance}m ({self._shorten_weapon(k.weapon)}) [{self._frame_to_timestamp(k.frame)}]"
            )

        # Vehicle kills
        vehicle_kills = [
            k for k in m.kills
            if isinstance(m.get_entity(k.victim_id), VehicleEntity)
        ]
        if vehicle_kills:
            lines.append("  Vehicle destructions:")
            for k in vehicle_kills:
                att = m.get_entity(k.attacker_id)
                vic = m.get_entity(k.victim_id)
                lines.append(
                    f"    {att.name if att else '?'} destroyed {vic.name if vic else '?'} "
                    f"({self._shorten_weapon(k.weapon)}, {k.distance}m) [{self._frame_to_timestamp(k.frame)}]"
                )

        return "\n".join(lines)

    def _enemy_composition(self) -> str:
        m = self.mission
        group_counts: Counter[str] = Counter()
        for e in m.entities.values():
            if not e.is_player and not isinstance(e, VehicleEntity):
                prefix = e.group.split(" ")[0] if e.group else "Ungrouped"
                group_counts[prefix] += 1

        lines = ["ENEMY FORCES:"]
        total = sum(group_counts.values())
        top = group_counts.most_common(5)
        for group, count in top:
            lines.append(f"  {group}: {count} personnel")
        lines.append(f"  Total non-player infantry: {total}")
        return "\n".join(lines)

    def _vehicle_assets(self) -> str:
        m = self.mission
        class_counts: Counter[str] = Counter()
        vehicle_names: dict[str, list[str]] = {}
        for e in m.entities.values():
            if isinstance(e, VehicleEntity):
                class_counts[e.vehicle_class] += 1
                vehicle_names.setdefault(e.vehicle_class, []).append(e.name)

        lines = ["VEHICLE ASSETS:"]
        for cls, count in class_counts.most_common():
            names = set(vehicle_names[cls])
            lines.append(f"  {cls}: {count}x ({', '.join(sorted(names)[:5])})")
        return "\n".join(lines)

    def _casualty_summary(self) -> str:
        m = self.mission
        player_ids = {p.id for p in m.players}

        # Count player kills on OPFOR
        blufor_kills = len([k for k in m.kills if k.attacker_id in player_ids and k.victim_id not in player_ids])
        player_deaths = len([k for k in m.kills if k.victim_id in player_ids])
        survived = len([p for p in m.players if p.death_frame is None])

        return (
            "FINAL STATUS:\n"
            f"  BLUFOR: {survived} survived, {player_deaths} KIA events\n"
            f"  OPFOR: {blufor_kills} confirmed KIA by players\n"
            f"  Total kills (all sources): {len(m.kills)}"
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _frame_to_timestamp(self, frame: int) -> str:
        seconds = frame * self.mission.capture_delay
        mins = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{mins:02d}:{secs:02d}"

    @staticmethod
    def _shorten_weapon(weapon: str) -> str:
        if not weapon:
            return "unknown"
        # Remove leading [XXX] prefix (e.g., "[121] Seekins..." or "[GOLD] m4a1...")
        text = weapon
        if text.startswith("[") and "] " in text:
            text = text.split("] ", 1)[1]
        # Strip parenthetical details
        base = text.split("(")[0].strip()
        # Extract final [caliber] from original text
        cal = ""
        if "[" in text:
            cal = text[text.rfind("["):]
        # Avoid duplicating caliber if base already ends with it
        if cal and not base.endswith(cal):
            return f"{base} {cal}"
        return base if base else weapon

    @staticmethod
    def _intensity_label(kill_count: int) -> str:
        if kill_count >= 20:
            return "Heavy contact"
        elif kill_count >= 10:
            return "Sustained engagement"
        elif kill_count >= 5:
            return "Moderate contact"
        else:
            return "Light contact"
