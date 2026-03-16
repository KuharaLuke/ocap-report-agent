"""Condenses a Mission object into a compact text briefing for LLM consumption."""

from __future__ import annotations

from collections import Counter

from models.entity import VehicleEntity
from models.event import KillEvent
from models.mission import Mission


class ReportBuilder:
    """Transforms parsed OCAP2 mission data into a structured briefing document.

    The output is designed to fit within ~2000 tokens so that a small LLM
    (e.g. Qwen 3.5 9B) can produce a coherent after-action report from it.
    Follows the TF405 AAR template structure.
    """

    NUM_PHASES = 5

    def __init__(self, mission: Mission, terrain_data: dict | None = None) -> None:
        self.mission = mission
        self.terrain_data = terrain_data
        self._terrain_tiles = terrain_data.get("tiles", {}) if terrain_data else {}
        self._terrain_zoom = terrain_data.get("zoom_level", 2) if terrain_data else 2
        self._world_size = (
            terrain_data.get("world_size")
            if terrain_data
            else None
        )

    def build(self) -> str:
        sections = [
            self._mission_header(),
            self._terrain_overview(),
            self._player_roster(),
            self._timeline_phases(),
            self._notable_engagements(),
            self._enemy_composition(),
            self._vehicle_assets(),
            self._casualty_summary(),
        ]
        return "\n\n".join(s for s in sections if s)

    # ------------------------------------------------------------------
    # Terrain helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _coords_to_grid(x: float, y: float) -> str:
        """Convert world coordinates to a 4-digit MGRS-style grid reference."""
        gx = max(0, int(x / 100))
        gy = max(0, int(y / 100))
        return f"{gx:02d}{gy:02d}"

    def _get_terrain_at(self, x: float, y: float) -> dict | None:
        """Look up terrain analysis for the tile containing world coords (x, y)."""
        if not self._terrain_tiles or not self._world_size:
            return None
        grid_size = 2 ** self._terrain_zoom
        tile_size = self._world_size / grid_size
        tile_x = min(int(x / tile_size), grid_size - 1)
        tile_y = min(int(y / tile_size), grid_size - 1)
        tile_x = max(0, tile_x)
        tile_y = max(0, tile_y)
        return self._terrain_tiles.get(f"{tile_x}_{tile_y}")

    def _describe_terrain(self, x: float, y: float) -> str:
        """Return a short terrain description for a position, or empty string."""
        tile = self._get_terrain_at(x, y)
        if not tile or tile.get("parse_error"):
            return ""
        terrain_type = tile.get("terrain_type", "")
        features = tile.get("geological_features", [])
        feature_types = [f.get("type", "") for f in features[:2]]
        parts = [terrain_type] if terrain_type else []
        if feature_types:
            parts.append("/".join(feature_types) + " terrain")
        return ", ".join(parts) if parts else ""

    def _kill_position(self, kill: KillEvent) -> tuple[float, float] | None:
        """Get the victim's world position at the frame of a kill event."""
        m = self.mission
        victim = m.get_entity(kill.victim_id)
        if not victim:
            return None
        pos = victim.position_at(kill.frame)
        if not pos:
            return None
        return (pos.x, pos.y)

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

    def _terrain_overview(self) -> str:
        """AO terrain summary from terrain analysis data."""
        if not self.terrain_data:
            return ""
        summary = self.terrain_data.get("summary", {})
        if not summary:
            return ""

        dominant = summary.get("dominant_terrain", "unknown")
        dist = summary.get("terrain_distribution", {})
        has_urban = summary.get("has_urban_areas", False)
        has_water = summary.get("has_water", False)
        building_count = summary.get("building_count", 0)
        geo_count = summary.get("geological_feature_count", 0)

        terrain_types = ", ".join(
            f"{t} ({c})" for t, c in sorted(dist.items(), key=lambda x: -x[1])
        )

        parts = [f"AO TERRAIN: Dominant terrain type: {dominant}."]
        if terrain_types:
            parts.append(f"  Distribution: {terrain_types}")
        features = []
        if has_urban:
            features.append("urban areas present")
        if has_water:
            features.append("water features present")
        if building_count:
            features.append(f"{building_count} structures identified")
        if geo_count:
            features.append(f"{geo_count} geological features identified")
        if features:
            parts.append(f"  Features: {', '.join(features)}")

        return "\n".join(parts)

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

            # Determine terrain context for this phase
            terrain_line = self._phase_terrain_summary(phase_kills)

            # Player casualties in this phase
            player_deaths = []
            for k in phase_kills:
                victim = m.get_entity(k.victim_id)
                if victim and victim.is_player:
                    att = m.get_entity(k.attacker_id)
                    att_name = att.name if att else "Unknown"
                    weapon = self._shorten_weapon(k.weapon)
                    pos = self._kill_position(k)
                    grid = f" at grid {self._coords_to_grid(*pos)}" if pos else ""
                    terrain_desc = self._describe_terrain(*pos) if pos else ""
                    terrain_suffix = f" - {terrain_desc}" if terrain_desc else ""
                    if k.attacker_id == k.victim_id:
                        player_deaths.append(f"** {victim.name} self-killed ({weapon}){grid}{terrain_suffix}")
                    else:
                        player_deaths.append(
                            f"** {victim.name} KIA by {att_name} ({weapon}, {k.distance}m){grid}{terrain_suffix}"
                        )

            intensity = self._intensity_label(len(phase_kills))
            lines.append(
                f"  Phase {i+1} ({self._frame_to_timestamp(start)}-{self._frame_to_timestamp(end)}): "
                f"{len(phase_kills)} kills - {intensity}. {top_attackers}"
            )
            if terrain_line:
                lines.append(f"    {terrain_line}")
            for pd in player_deaths:
                lines.append(f"    {pd}")

        return "\n".join(lines)

    def _phase_terrain_summary(self, phase_kills: list) -> str:
        """Summarize the terrain types where kills occurred in a phase."""
        if not self._terrain_tiles:
            return ""
        terrain_counts: Counter[str] = Counter()
        grids: set[str] = set()
        for k in phase_kills:
            pos = self._kill_position(k)
            if not pos:
                continue
            grids.add(self._coords_to_grid(*pos))
            tile = self._get_terrain_at(*pos)
            if tile and not tile.get("parse_error"):
                terrain_counts[tile.get("terrain_type", "unknown")] += 1

        if not terrain_counts:
            return ""
        dominant = terrain_counts.most_common(1)[0][0]
        grid_list = sorted(grids)
        grid_range = f"{grid_list[0]}-{grid_list[-1]}" if len(grid_list) > 1 else grid_list[0]
        return f"Terrain: engagements in {dominant} terrain near grids {grid_range}"

    def _notable_engagements(self) -> str:
        m = self.mission
        lines = ["NOTABLE ENGAGEMENTS:"]

        # Top 3 longest kills
        valid_kills = [k for k in m.kills if k.distance > 0]
        longest = sorted(valid_kills, key=lambda k: k.distance, reverse=True)[:3]
        for k in longest:
            att = m.get_entity(k.attacker_id)
            vic = m.get_entity(k.victim_id)
            pos = self._kill_position(k)
            grid = f" at grid {self._coords_to_grid(*pos)}" if pos else ""
            terrain_desc = self._describe_terrain(*pos) if pos else ""
            terrain_suffix = f", {terrain_desc}" if terrain_desc else ""
            lines.append(
                f"  {att.name if att else '?'} killed {vic.name if vic else '?'} "
                f"at {k.distance}m ({self._shorten_weapon(k.weapon)}) "
                f"[{self._frame_to_timestamp(k.frame)}]{grid}{terrain_suffix}"
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
                pos = self._kill_position(k)
                grid = f" at grid {self._coords_to_grid(*pos)}" if pos else ""
                lines.append(
                    f"    {att.name if att else '?'} destroyed {vic.name if vic else '?'} "
                    f"({self._shorten_weapon(k.weapon)}, {k.distance}m) "
                    f"[{self._frame_to_timestamp(k.frame)}]{grid}"
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
        text = weapon
        if text.startswith("[") and "] " in text:
            text = text.split("] ", 1)[1]
        base = text.split("(")[0].strip()
        cal = ""
        if "[" in text:
            cal = text[text.rfind("["):]
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
