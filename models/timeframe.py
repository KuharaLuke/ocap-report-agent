from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True)
class TimeFrame:
    """A time reference point mapping frame numbers to real/game time."""

    date: str
    frame_num: int
    system_time_utc: str
    time: float
    time_multiplier: float

    @classmethod
    def from_dict(cls, d: dict) -> TimeFrame:
        return cls(
            date=d["date"],
            frame_num=d["frameNum"],
            system_time_utc=d["systemTimeUTC"],
            time=d["time"],
            time_multiplier=d["timeMultiplier"],
        )

    @property
    def game_datetime(self) -> datetime:
        return datetime.fromisoformat(self.date)

    @property
    def real_datetime(self) -> datetime:
        return datetime.fromisoformat(self.system_time_utc)
