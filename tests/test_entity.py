from math import sqrt

from aar_pipeline.models.entity import Entity, InfantryEntity, VehicleEntity
from aar_pipeline.models.position import PositionFrame


def _make_raw_infantry():
    return {
        "id": 42,
        "isPlayer": 1,
        "name": "Sgt Test",
        "group": "Alpha 1-1",
        "role": "5: Engineer",
        "positions": [
            [[100, 200, 30], 90, 1, 0, "Sgt Test", 1, "5: Engineer"],
            [[105, 205, 30], 95, 1, 0, "Sgt Test", 1, "5: Engineer"],
            [[110, 210, 30], 100, 0, 0, "Sgt Test", 1, "5: Engineer"],
        ],
        "framesFired": [
            [0, [100, 200, 31]],
            [1, [105, 205, 31]],
        ],
    }


def _make_raw_vehicle():
    return {
        "id": 300,
        "class": "tank",
        "name": "T-55A",
        "group": "",
        "positions": [
            [[500, 600, 40], 180, 1, 0, "T-55A", 0, ""],
        ],
        "framesFired": [],
    }


class TestEntityFactory:

    def test_from_dict_infantry(self):
        e = Entity.from_dict(_make_raw_infantry())
        assert isinstance(e, InfantryEntity)
        assert e.id == 42
        assert e.is_player is True
        assert e.name == "Sgt Test"
        assert e.group == "Alpha 1-1"
        assert e.role == "5: Engineer"

    def test_from_dict_vehicle(self):
        e = Entity.from_dict(_make_raw_vehicle())
        assert isinstance(e, VehicleEntity)
        assert e.vehicle_class == "tank"
        assert e.name == "T-55A"
        assert e.id == 300


class TestEntityMethods:

    def test_position_at_valid(self):
        e = Entity.from_dict(_make_raw_infantry())
        pos = e.position_at(0)
        assert isinstance(pos, PositionFrame)
        assert pos.x == 100

    def test_position_at_invalid(self):
        e = Entity.from_dict(_make_raw_infantry())
        assert e.position_at(-1) is None
        assert e.position_at(999) is None

    def test_is_alive_at(self):
        e = Entity.from_dict(_make_raw_infantry())
        assert e.is_alive_at(0) is True
        assert e.is_alive_at(1) is True
        assert e.is_alive_at(2) is False

    def test_death_frame(self):
        e = Entity.from_dict(_make_raw_infantry())
        assert e.death_frame == 2

    def test_death_frame_survives(self):
        raw = _make_raw_vehicle()
        e = Entity.from_dict(raw)
        assert e.death_frame is None

    def test_total_shots(self):
        e = Entity.from_dict(_make_raw_infantry())
        assert e.total_shots == 2

    def test_distance_to(self):
        e1 = Entity.from_dict(_make_raw_infantry())
        e2 = Entity.from_dict(_make_raw_vehicle())
        dist = e1.distance_to(e2, 0)
        expected = sqrt((100 - 500) ** 2 + (200 - 600) ** 2 + (30 - 40) ** 2)
        assert dist is not None
        assert abs(dist - expected) < 0.01

    def test_str_infantry(self):
        e = Entity.from_dict(_make_raw_infantry())
        s = str(e)
        assert "[P]" in s
        assert "Sgt Test" in s

    def test_str_vehicle(self):
        e = Entity.from_dict(_make_raw_vehicle())
        s = str(e)
        assert "Vehicle:tank" in s
        assert "T-55A" in s


class TestEntityRealData:

    def test_player_positions_length(self, mission):
        """Each player should have positions for every frame up to end_frame."""
        for player in mission.players:
            assert len(player.positions) > 0

    def test_vehicle_entities_have_class(self, mission):
        vehicles = [e for e in mission.entities.values() if isinstance(e, VehicleEntity)]
        assert len(vehicles) > 0
        for v in vehicles:
            assert v.vehicle_class in ("car", "apc", "tank", "static-weapon")
