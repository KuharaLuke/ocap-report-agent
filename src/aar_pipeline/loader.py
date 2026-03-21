from __future__ import annotations

import gzip
import json
from pathlib import Path

from .models.entity import Entity
from .models.event import Event
from .models.marker import Marker
from .models.mission import Mission
from .models.timeframe import TimeFrame


class MissionLoader:
    """Loads an OCAP2 .json.gz mission replay file into a Mission object."""

    @staticmethod
    def load(filepath: str | Path) -> Mission:
        filepath = Path(filepath)

        if filepath.suffix == ".gz":
            with gzip.open(filepath, "rt", encoding="utf-8") as f:
                raw = json.load(f)
        else:
            with open(filepath, "r", encoding="utf-8") as f:
                raw = json.load(f)

        mission = Mission(
            addon_version=raw.get("addonVersion", ""),
            capture_delay=raw.get("captureDelay", 0.0),
            end_frame=raw.get("endFrame", 0),
            extension_build=raw.get("extensionBuild", ""),
            extension_version=raw.get("extensionVersion", ""),
            mission_author=raw.get("missionAuthor", ""),
            mission_name=raw.get("missionName", ""),
            world_name=raw.get("worldName", ""),
        )

        # Parse entities
        for entity_data in raw.get("entities", []):
            entity = Entity.from_dict(entity_data)
            mission.entities[entity.id] = entity

        # Parse events
        for event_data in raw.get("events", []):
            mission.events.append(Event.from_raw(event_data))

        # Parse times
        for time_data in raw.get("times", []):
            mission.times.append(TimeFrame.from_dict(time_data))

        # Parse markers
        for marker_data in raw.get("Markers", []):
            mission.markers.append(Marker.from_raw(marker_data))

        return mission
