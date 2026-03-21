from aar_pipeline.models.position import PositionFrame


class TestPositionFrame:

    def test_from_raw(self):
        raw = [[100.5, 200.3, 50.1], 90, 1, 0, "TestUnit", 1, "Rifleman"]
        pf = PositionFrame.from_raw(raw)
        assert pf.x == 100.5
        assert pf.y == 200.3
        assert pf.z == 50.1
        assert pf.direction == 90
        assert pf.alive == 1
        assert pf.in_vehicle == 0
        assert pf.name == "TestUnit"
        assert pf.is_player == 1
        assert pf.role == "Rifleman"

    def test_is_alive_true(self):
        pf = PositionFrame(1, 2, 3, 0, 1, 0, "u", 0, "")
        assert pf.is_alive is True

    def test_is_alive_false(self):
        pf = PositionFrame(1, 2, 3, 0, 0, 0, "u", 0, "")
        assert pf.is_alive is False

    def test_coords(self):
        pf = PositionFrame(10.0, 20.0, 30.0, 0, 1, 0, "u", 0, "")
        assert pf.coords == (10.0, 20.0, 30.0)

    def test_coords_2d(self):
        pf = PositionFrame(10.0, 20.0, 30.0, 0, 1, 0, "u", 0, "")
        assert pf.coords_2d == (10.0, 20.0)

    def test_from_raw_real_data(self, mission):
        """Parse a real entity's first position frame."""
        entity = mission.get_entity(0)
        assert entity is not None
        pos = entity.positions[0]
        assert isinstance(pos, PositionFrame)
        assert isinstance(pos.x, float)
        assert isinstance(pos.y, float)
        assert pos.name != ""
