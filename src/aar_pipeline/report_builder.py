"""Condenses a Mission object into a compact text briefing for LLM consumption."""

from __future__ import annotations

import math
from collections import Counter

from .models.entity import VehicleEntity
from .models.event import ConnectionEvent, KillEvent
from .models.mission import Mission


class ReportBuilder:
    """Transforms parsed OCAP2 mission data into a structured briefing document.

    The output is designed to fit within the context window of a local LLM
    (e.g. Qwen 3.5 9B @ 32K context) while maximising useful information.
    Follows the TF405 AAR template structure.
    """

    def __init__(
        self,
        mission: Mission,
        terrain_data: dict | None = None,
        cities: list[dict] | None = None,
        discord_context: str | None = None,
    ) -> None:
        self.mission = mission
        self.terrain_data = terrain_data
        self._terrain_tiles = terrain_data.get("tiles", {}) if terrain_data else {}
        self._terrain_zoom = terrain_data.get("zoom_level", 2) if terrain_data else 2
        self._world_size = (
            terrain_data.get("world_size")
            if terrain_data
            else None
        )
        self._cities = cities or []
        self._discord_context = discord_context
        # Pre-compute disconnect frames for artifact detection
        self._disconnect_frames = {
            e.frame for e in mission.events
            if isinstance(e, ConnectionEvent) and e.event_type == "disconnected"
        }
        # Pre-compute player IDs for reuse
        self._player_ids = {p.id for p in mission.players}

    def build(self) -> str:
        sections = [
            self._mission_header(),
            self._terrain_overview(),
            self._discord_intel(),
            self._player_roster(),
            self._timeline_phases(),
            self._notable_engagements(),
            self._enemy_composition(),
            self._vehicle_assets(),
            self._casualty_summary(),
        ]
        return "\n\n".join(s for s in sections if s)

    # ------------------------------------------------------------------
    # Kill filtering
    # ------------------------------------------------------------------

    def _is_artifact(self, kill: KillEvent) -> bool:
        """Detect OCAP2 non-combat kill artifacts that should be excluded.

        Covers:
        - Respawn/teleport: self-kill with empty weapon
        - Disconnect: self-kill at same frame as a disconnect event
        - Environmental/scripted: attacker_id=-1, empty weapon, distance=-1
        """
        weapon = kill.weapon.strip() if kill.weapon else ""
        weapon_empty = weapon in ("", "[]")

        # Self-kill checks
        if kill.victim_id == kill.attacker_id:
            if weapon_empty:
                return True  # respawn/teleport artifact
            # Check for disconnect at same frame
            if kill.distance == 0 and kill.frame in self._disconnect_frames:
                return True

        # Unknown attacker with no weapon = environmental/scripted death
        if kill.attacker_id == -1 and weapon_empty and kill.distance == -1:
            return True

        return False

    @property
    def _combat_kills(self) -> list[KillEvent]:
        """All kills excluding non-combat artifacts."""
        return [k for k in self.mission.kills if not self._is_artifact(k)]

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

    def _nearest_city(self, x: float, y: float, max_distance: float = 2000.0) -> str:
        """Return 'near CityName' if within max_distance, else empty string."""
        best_name = ""
        best_dist = max_distance
        for city in self._cities:
            dx = x - city["x"]
            dy = y - city["y"]
            dist = (dx * dx + dy * dy) ** 0.5
            if dist < best_dist:
                best_dist = dist
                best_name = city["name"]
        return f"near {best_name}" if best_name else ""

    def _grid_with_city(self, x: float, y: float) -> str:
        """Return 'grid XXYY' with optional 'near CityName' suffix."""
        grid = self._coords_to_grid(x, y)
        city = self._nearest_city(x, y)
        return f"grid {grid} {city}".rstrip() if city else f"grid {grid}"

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

    def _discord_intel(self) -> str:
        """Include Discord-sourced pre-mission intelligence if available."""
        if not self._discord_context:
            return ""
        return f"PRE-MISSION INTELLIGENCE (from planning channel):\n{self._discord_context}"

    def _merged_players(self) -> list[dict]:
        """Merge duplicate player entities (reconnections) by name."""
        m = self.mission
        merged: dict[str, dict] = {}
        for p in m.players:
            if p.name not in merged:
                merged[p.name] = {
                    "name": p.name,
                    "role": p.role,
                    "ids": [p.id],
                    "entity": p,
                }
            else:
                merged[p.name]["ids"].append(p.id)
                # Keep the role from the entity with more kills
                if len(self._player_kills_by(p.id)) > len(self._player_kills_by(merged[p.name]["entity"].id)):
                    merged[p.name]["role"] = p.role
                    merged[p.name]["entity"] = p
        return list(merged.values())

    def _player_kills_by(self, entity_id: int) -> list[KillEvent]:
        """Kills by an entity, excluding respawn artifacts."""
        return [k for k in self.mission.kills_by(entity_id) if not self._is_artifact(k)]

    def _player_deaths_of(self, entity_id: int) -> list[KillEvent]:
        """Deaths of an entity, excluding respawn artifacts."""
        return [k for k in self.mission.deaths_of(entity_id) if not self._is_artifact(k)]

    def _player_roster(self) -> str:
        m = self.mission
        lines = ["FRIENDLY FORCES:"]
        for info in self._merged_players():
            ids = info["ids"]
            kills = sum(len(self._player_kills_by(eid)) for eid in ids)
            deaths = sum(len(self._player_deaths_of(eid)) for eid in ids)
            total_shots = sum(m.get_entity(eid).total_shots for eid in ids)
            total_hits = sum(
                len([h for h in m.hits if h.attacker_id == eid]) for eid in ids
            )
            if total_shots > 0:
                acc = f"{total_hits / total_shots * 100:.0f}%"
            elif total_hits > 0:
                acc = f"{total_hits} hits"
            else:
                acc = "N/A"
            status = self._merged_player_status(info)
            lines.append(
                f"  {info['name']:<22} | {info['role']:<22} | {kills}K/{deaths}D | {acc} acc | {status}"
            )
        return "\n".join(lines)

    def _merged_player_status(self, info: dict) -> str:
        """Determine status from filtered kill events, not position data."""
        # Collect real (non-artifact) deaths across all entity IDs
        all_deaths = []
        for eid in info["ids"]:
            all_deaths.extend(self._player_deaths_of(eid))

        if not all_deaths:
            return "Survived"

        # Sort by frame to find earliest real death
        all_deaths.sort(key=lambda k: k.frame)
        first = all_deaths[0]
        ts = self._frame_to_timestamp(first.frame)

        # Check if they continued fighting after their first real death
        all_kills = []
        for eid in info["ids"]:
            all_kills.extend(self._player_kills_by(eid))
        later_kills = [k for k in all_kills if k.frame > first.frame]

        if later_kills or len(all_deaths) > 1:
            return f"KIA {ts}, returned to action"
        return f"KIA {ts}"

    # ------------------------------------------------------------------
    # Adaptive timeline
    # ------------------------------------------------------------------

    @property
    def _num_phases(self) -> int:
        """Adaptive phase count: ~10 minutes per phase, clamped to [3, 12]."""
        duration_minutes = self.mission.duration_seconds / 60
        return max(3, min(12, round(duration_minutes / 10)))

    def _timeline_phases(self) -> str:
        m = self.mission
        num_phases = self._num_phases
        phase_size = max(1, m.end_frame // num_phases)
        kills = self._combat_kills
        lines = ["TIMELINE:"]

        for i in range(num_phases):
            start = i * phase_size
            end = (i + 1) * phase_size if i < num_phases - 1 else m.end_frame
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
                    grid = f" at {self._grid_with_city(*pos)}" if pos else ""
                    terrain_desc = self._describe_terrain(*pos) if pos else ""
                    terrain_suffix = f" - {terrain_desc}" if terrain_desc else ""
                    if k.attacker_id == k.victim_id:
                        player_deaths.append(f"** {victim.name} self-killed ({weapon}){grid}{terrain_suffix}")
                    else:
                        player_deaths.append(
                            f"** {victim.name} KIA by {att_name} ({weapon}, {k.distance}m){grid}{terrain_suffix}"
                        )

            # Movement summary for this phase
            movement = self._phase_movement_summary(start, end)

            intensity = self._intensity_label(len(phase_kills))
            lines.append(
                f"  Phase {i+1} ({self._frame_to_timestamp(start)}-{self._frame_to_timestamp(end)}): "
                f"{len(phase_kills)} kills - {intensity}. {top_attackers}"
            )
            if terrain_line:
                lines.append(f"    {terrain_line}")
            if movement:
                lines.append(f"    {movement}")
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

    def _phase_movement_summary(self, start_frame: int, end_frame: int) -> str:
        """Describe player force movement during a phase."""
        # Group players by element designation (from role prefix)
        elements: dict[str, list] = {}
        for info in self._merged_players():
            entity = info["entity"]
            role = info["role"] or ""
            # Extract element designation: "1-1 Squad Leader" -> "1-1"
            prefix = role.split()[0] if role else "HQ"
            elements.setdefault(prefix, []).append(entity)

        movements = []
        for element_name, entities in elements.items():
            for entity in entities:
                start_pos = entity.position_at(start_frame)
                end_pos = entity.position_at(end_frame)
                if start_pos and end_pos:
                    start_grid = self._coords_to_grid(start_pos.x, start_pos.y)
                    end_grid = self._coords_to_grid(end_pos.x, end_pos.y)
                    if start_grid != end_grid:
                        direction = self._bearing_label(
                            start_pos.x, start_pos.y, end_pos.x, end_pos.y
                        )
                        movements.append(
                            f"{element_name}: {direction} from {self._grid_with_city(start_pos.x, start_pos.y)}"
                            f" to {self._grid_with_city(end_pos.x, end_pos.y)}"
                        )
                    break  # one entity per element is enough
        if not movements:
            return ""
        return "Movement: " + "; ".join(movements)

    def _notable_engagements(self) -> str:
        m = self.mission
        lines = ["NOTABLE ENGAGEMENTS:"]

        # Top 3 longest kills
        valid_kills = [k for k in self._combat_kills if k.distance > 0]
        longest = sorted(valid_kills, key=lambda k: k.distance, reverse=True)[:3]
        for k in longest:
            att = m.get_entity(k.attacker_id)
            vic = m.get_entity(k.victim_id)
            pos = self._kill_position(k)
            grid = f" at {self._grid_with_city(*pos)}" if pos else ""
            terrain_desc = self._describe_terrain(*pos) if pos else ""
            terrain_suffix = f", {terrain_desc}" if terrain_desc else ""
            lines.append(
                f"  {att.name if att else '?'} killed {vic.name if vic else '?'} "
                f"at {k.distance}m ({self._shorten_weapon(k.weapon)}) "
                f"[{self._frame_to_timestamp(k.frame)}]{grid}{terrain_suffix}"
            )

        # Vehicle kills
        vehicle_kills = [
            k for k in self._combat_kills
            if isinstance(m.get_entity(k.victim_id), VehicleEntity)
        ]
        if vehicle_kills:
            lines.append("  Vehicle destructions:")
            for k in vehicle_kills:
                att = m.get_entity(k.attacker_id)
                vic = m.get_entity(k.victim_id)
                pos = self._kill_position(k)
                grid = f" at {self._grid_with_city(*pos)}" if pos else ""
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

        # Enemy weapon types from kill events where attacker is non-player
        enemy_weapons: Counter[str] = Counter()
        for k in self._combat_kills:
            if k.attacker_id not in self._player_ids and k.attacker_id != -1:
                weapon = self._shorten_weapon(k.weapon)
                if weapon and weapon != "unknown":
                    enemy_weapons[weapon] += 1

        lines = ["ENEMY FORCES:"]
        total = sum(group_counts.values())
        top = group_counts.most_common(5)
        for group, count in top:
            lines.append(f"  {group}: {count} personnel")
        lines.append(f"  Total non-player infantry: {total}")

        if enemy_weapons:
            lines.append("  Observed enemy weapons:")
            for weapon, count in enemy_weapons.most_common(8):
                lines.append(f"    {weapon}: {count} kills")

        return "\n".join(lines)

    def _vehicle_assets(self) -> str:
        m = self.mission
        player_groups = {
            p.group.split(" ")[0] for p in m.players if p.group
        }

        friendly_vehicles: Counter[str] = Counter()
        friendly_names: dict[str, set] = {}
        enemy_vehicles: Counter[str] = Counter()
        enemy_names: dict[str, set] = {}
        unclassified_vehicles: Counter[str] = Counter()
        unclassified_names: dict[str, set] = {}

        for e in m.entities.values():
            if not isinstance(e, VehicleEntity):
                continue
            veh_prefix = e.group.split(" ")[0] if e.group else ""
            if not veh_prefix:
                target_counter = unclassified_vehicles
                target_names = unclassified_names
            elif veh_prefix in player_groups:
                target_counter = friendly_vehicles
                target_names = friendly_names
            else:
                target_counter = enemy_vehicles
                target_names = enemy_names
            target_counter[e.vehicle_class] += 1
            target_names.setdefault(e.vehicle_class, set()).add(e.name)

        lines = ["VEHICLE ASSETS:"]
        if friendly_vehicles:
            lines.append("  FRIENDLY:")
            for cls, count in friendly_vehicles.most_common():
                names = sorted(friendly_names[cls])[:5]
                lines.append(f"    {cls}: {count}x ({', '.join(names)})")
        if enemy_vehicles:
            lines.append("  ENEMY:")
            for cls, count in enemy_vehicles.most_common():
                names = sorted(enemy_names[cls])[:5]
                lines.append(f"    {cls}: {count}x ({', '.join(names)})")
        if unclassified_vehicles:
            # If there are also classified vehicles, label this section;
            # otherwise just list them flat (no misleading ENEMY label)
            if friendly_vehicles or enemy_vehicles:
                lines.append("  UNCLASSIFIED:")
            for cls, count in unclassified_vehicles.most_common():
                names = sorted(unclassified_names[cls])[:5]
                prefix = "    " if friendly_vehicles or enemy_vehicles else "  "
                lines.append(f"{prefix}{cls}: {count}x ({', '.join(names)})")
        if not friendly_vehicles and not enemy_vehicles and not unclassified_vehicles:
            lines.append("  No vehicles recorded")
        return "\n".join(lines)

    def _casualty_summary(self) -> str:
        m = self.mission
        combat = self._combat_kills

        blufor_kills = len([k for k in combat if k.attacker_id in self._player_ids and k.victim_id not in self._player_ids])
        player_deaths = len([k for k in combat if k.victim_id in self._player_ids])
        # Count survivors based on filtered kill events, not position data
        merged = self._merged_players()
        kia_names = set()
        for info in merged:
            deaths = []
            for eid in info["ids"]:
                deaths.extend(self._player_deaths_of(eid))
            if deaths:
                # Check if they returned to action (kills after death)
                all_kills_after = []
                for eid in info["ids"]:
                    for k in self._player_kills_by(eid):
                        if any(k.frame > d.frame for d in deaths):
                            all_kills_after.append(k)
                if not all_kills_after and len(deaths) == 1:
                    kia_names.add(info["name"])
        survived = len(merged) - len(kia_names)

        return (
            "FINAL STATUS:\n"
            f"  BLUFOR: {survived} survived, {player_deaths} KIA events\n"
            f"  OPFOR: {blufor_kills} confirmed KIA by players\n"
            f"  Total kills (all sources): {len(combat)}"
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

    @staticmethod
    def _bearing_label(x1: float, y1: float, x2: float, y2: float) -> str:
        """Convert a movement vector to a compass direction label."""
        dx = x2 - x1
        dy = y2 - y1
        if abs(dx) < 50 and abs(dy) < 50:
            return "held position"
        # Arma coordinate system: x = east, y = north
        angle = math.degrees(math.atan2(dx, dy)) % 360
        directions = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
        idx = round(angle / 45) % 8
        return f"moved {directions[idx]}"
