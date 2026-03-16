from models.marker import Marker


class TestMarker:

    def test_from_raw_full(self):
        raw = [
            "mil_dot", "Test Label", 10, 50, 100, "FF0000", -1,
            [[10, [100, 200, 30], 0.0, 1]], [1, 1], "ICON", "Solid"
        ]
        m = Marker.from_raw(raw)
        assert m.icon == "mil_dot"
        assert m.label == "Test Label"
        assert m.start_frame == 10
        assert m.end_frame == 50
        assert m.entity_id == 100
        assert m.color == "FF0000"
        assert len(m.positions) == 1
        assert m.size == [1, 1]
        assert m.shape == "ICON"
        assert m.brush == "Solid"

    def test_from_raw_minimal(self):
        raw = ["icon", "label", 0, 10, -1, "000000", -1]
        m = Marker.from_raw(raw)
        assert m.icon == "icon"
        assert m.positions == []
        assert m.size == []
        assert m.shape == ""
        assert m.brush == ""

    def test_real_data_markers_populated(self, mission):
        assert len(mission.markers) > 0
        for m in mission.markers[:10]:
            assert isinstance(m.icon, str)
            assert isinstance(m.start_frame, int)
