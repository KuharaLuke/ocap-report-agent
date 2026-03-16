from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Event:
    """Base class for mission events."""

    frame: int
    event_type: str

    @classmethod
    def _parse_attacker(cls, field) -> tuple:
        """Extract (attacker_id, weapon) from the attacker field.

        Formats: [attackerId, weapon], ['null'], or bare int.
        """
        if isinstance(field, list):
            aid = field[0] if len(field) > 0 else -1
            if aid == "null":
                aid = -1
            weapon = field[1] if len(field) > 1 else ""
            return aid, weapon
        return field, ""

    @classmethod
    def from_raw(cls, raw: list) -> Event:
        frame = raw[0]
        etype = raw[1]

        if etype == "hit":
            aid, weapon = cls._parse_attacker(raw[3])
            return HitEvent(
                frame=frame,
                event_type=etype,
                victim_id=raw[2],
                attacker_id=aid,
                weapon=weapon,
                distance=raw[4] if len(raw) > 4 else 0,
            )
        elif etype == "killed":
            aid, weapon = cls._parse_attacker(raw[3])
            return KillEvent(
                frame=frame,
                event_type=etype,
                victim_id=raw[2],
                attacker_id=aid,
                weapon=weapon,
                distance=raw[4] if len(raw) > 4 else 0,
            )
        elif etype == "generalEvent":
            return GeneralEvent(
                frame=frame,
                event_type=etype,
                message=raw[2] if len(raw) > 2 else "",
            )
        elif etype in ("connected", "disconnected"):
            return ConnectionEvent(
                frame=frame,
                event_type=etype,
                player_id=raw[2] if len(raw) > 2 else -1,
            )
        else:
            return Event(frame=frame, event_type=etype)


@dataclass
class HitEvent(Event):
    """An entity was hit by a weapon."""

    victim_id: int = -1
    attacker_id: int = -1
    weapon: str = ""
    distance: float = 0.0


@dataclass
class KillEvent(Event):
    """An entity was killed."""

    victim_id: int = -1
    attacker_id: int = -1
    weapon: str = ""
    distance: float = 0.0


@dataclass
class GeneralEvent(Event):
    """A general mission event (mission start, recording, etc.)."""

    message: str = ""


@dataclass
class ConnectionEvent(Event):
    """A player connected or disconnected."""

    player_id: int = -1
