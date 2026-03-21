from __future__ import annotations

from dataclasses import dataclass, field
from math import sqrt

from .position import PositionFrame


@dataclass
class Entity:
    """Base class for all tracked entities (infantry and vehicles)."""

    id: int
    name: str
    group: str
    is_player: bool
    role: str
    positions: list[PositionFrame] = field(default_factory=list, repr=False)
    frames_fired: list[tuple[int, tuple[float, float, float]]] = field(
        default_factory=list, repr=False
    )

    @classmethod
    def from_dict(cls, d: dict) -> Entity:
        positions = [PositionFrame.from_raw(p) for p in d.get("positions", [])]
        frames_fired = [
            (ff[0], tuple(ff[1])) for ff in d.get("framesFired", [])
        ]

        common = dict(
            id=d["id"],
            name=d.get("name", ""),
            group=d.get("group", ""),
            is_player=bool(d.get("isPlayer", 0)),
            role=d.get("role", ""),
            positions=positions,
            frames_fired=frames_fired,
        )

        if "class" in d:
            return VehicleEntity(vehicle_class=d["class"], **common)
        return InfantryEntity(**common)

    def position_at(self, frame: int) -> PositionFrame | None:
        if 0 <= frame < len(self.positions):
            return self.positions[frame]
        return None

    def is_alive_at(self, frame: int) -> bool:
        pos = self.position_at(frame)
        return pos.is_alive if pos else False

    @property
    def total_shots(self) -> int:
        return len(self.frames_fired)

    @property
    def first_frame(self) -> int:
        """Frame index where this entity first appears."""
        return 0

    @property
    def last_frame(self) -> int:
        return len(self.positions) - 1

    @property
    def death_frame(self) -> int | None:
        """Frame where entity transitions from alive to dead, or None."""
        for i in range(1, len(self.positions)):
            if self.positions[i - 1].is_alive and not self.positions[i].is_alive:
                return i
        return None

    def distance_to(self, other: Entity, frame: int) -> float | None:
        a = self.position_at(frame)
        b = other.position_at(frame)
        if a and b:
            dx = a.x - b.x
            dy = a.y - b.y
            dz = a.z - b.z
            return sqrt(dx * dx + dy * dy + dz * dz)
        return None

    def __str__(self) -> str:
        tag = "P" if self.is_player else "AI"
        return f"[{tag}] {self.name} (id={self.id}, group={self.group})"


@dataclass
class InfantryEntity(Entity):
    """A soldier / infantry unit."""
    pass


@dataclass
class VehicleEntity(Entity):
    """A vehicle (car, apc, tank, static-weapon)."""

    vehicle_class: str = ""

    def __str__(self) -> str:
        return f"[Vehicle:{self.vehicle_class}] {self.name} (id={self.id})"
