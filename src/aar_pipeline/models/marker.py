from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Marker:
    """A map marker from the mission replay.

    Raw format: [icon, label, start_frame, end_frame, entity_id, color, unknown,
                 positions_over_frames, size, shape, brush]
    """

    icon: str
    label: str
    start_frame: int
    end_frame: int
    entity_id: int
    color: str
    positions: list[list] = field(default_factory=list, repr=False)
    size: list[float] = field(default_factory=list)
    shape: str = ""
    brush: str = ""

    @classmethod
    def from_raw(cls, raw: list) -> Marker:
        return cls(
            icon=raw[0],
            label=raw[1],
            start_frame=raw[2],
            end_frame=raw[3],
            entity_id=raw[4],
            color=raw[5],
            # raw[6] is an unknown/-1 field, skip
            positions=raw[7] if len(raw) > 7 else [],
            size=raw[8] if len(raw) > 8 else [],
            shape=raw[9] if len(raw) > 9 else "",
            brush=raw[10] if len(raw) > 10 else "",
        )
