from __future__ import annotations

from dataclasses import dataclass, field

from .entity import Entity
from .event import Event, HitEvent, KillEvent
from .marker import Marker
from .timeframe import TimeFrame


@dataclass
class Mission:
    """Top-level container for an entire Arma 3 mission replay."""

    # Metadata
    addon_version: str = ""
    capture_delay: float = 0.0
    end_frame: int = 0
    extension_build: str = ""
    extension_version: str = ""
    mission_author: str = ""
    mission_name: str = ""
    world_name: str = ""

    # Data collections
    entities: dict[int, Entity] = field(default_factory=dict)
    events: list[Event] = field(default_factory=list)
    times: list[TimeFrame] = field(default_factory=list)
    markers: list[Marker] = field(default_factory=list)

    # --- Query methods ---

    @property
    def players(self) -> list[Entity]:
        return [e for e in self.entities.values() if e.is_player]

    def get_entity(self, entity_id: int) -> Entity | None:
        return self.entities.get(entity_id)

    @property
    def kills(self) -> list[KillEvent]:
        return [e for e in self.events if isinstance(e, KillEvent)]

    @property
    def hits(self) -> list[HitEvent]:
        return [e for e in self.events if isinstance(e, HitEvent)]

    def events_for_entity(self, entity_id: int) -> list[Event]:
        """Return all events where entity_id is the victim or attacker."""
        result = []
        for ev in self.events:
            if isinstance(ev, (HitEvent, KillEvent)):
                if ev.victim_id == entity_id or ev.attacker_id == entity_id:
                    result.append(ev)
        return result

    def kills_by(self, entity_id: int) -> list[KillEvent]:
        return [k for k in self.kills if k.attacker_id == entity_id]

    def deaths_of(self, entity_id: int) -> list[KillEvent]:
        return [k for k in self.kills if k.victim_id == entity_id]

    def frame_to_time(self, frame: int) -> TimeFrame | None:
        """Find the closest TimeFrame for a given frame number."""
        best = None
        for t in self.times:
            if t.frame_num <= frame:
                best = t
            else:
                break
        return best

    @property
    def duration_seconds(self) -> float:
        if self.times:
            return self.times[-1].time - self.times[0].time
        return 0.0

    def __str__(self) -> str:
        return (
            f"Mission: {self.mission_name} on {self.world_name}\n"
            f"  Author: {self.mission_author}\n"
            f"  Frames: 0-{self.end_frame} (capture every {self.capture_delay}s)\n"
            f"  Entities: {len(self.entities)} ({len(self.players)} players)\n"
            f"  Events: {len(self.events)} ({len(self.kills)} kills, {len(self.hits)} hits)\n"
            f"  Markers: {len(self.markers)}"
        )
