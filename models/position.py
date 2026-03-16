from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class PositionFrame:
    """A single frame snapshot of an entity's position and state.

    Raw format: [[x, y, z], direction, alive, in_vehicle, name, is_player, role]
    """

    x: float
    y: float
    z: float
    direction: float
    alive: int
    in_vehicle: int
    name: str
    is_player: int
    role: str

    @classmethod
    def from_raw(cls, raw: list) -> PositionFrame:
        """Parse a position frame from raw list data.

        Long format (infantry):  [[x,y,z], dir, alive, in_vehicle, name, is_player, role]
        Short format (vehicle):  [[x,y,z], dir, alive, [crew_ids], [start, end]]
        """
        coords = raw[0]
        if len(raw) >= 7:
            in_vehicle = raw[3]
            name = raw[4]
            is_player = raw[5]
            role = raw[6]
        else:
            in_vehicle = raw[3] if len(raw) > 3 else 0
            name = ""
            is_player = 0
            role = ""
        return cls(
            x=coords[0],
            y=coords[1],
            z=coords[2],
            direction=raw[1],
            alive=raw[2],
            in_vehicle=in_vehicle,
            name=name,
            is_player=is_player,
            role=role,
        )

    @property
    def is_alive(self) -> bool:
        return self.alive == 1

    @property
    def coords(self) -> tuple[float, float, float]:
        return (self.x, self.y, self.z)

    @property
    def coords_2d(self) -> tuple[float, float]:
        return (self.x, self.y)
