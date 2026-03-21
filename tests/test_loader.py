import json

from aar_pipeline.models.entity import VehicleEntity
from aar_pipeline.models.event import KillEvent, HitEvent, GeneralEvent


class TestLoaderBasic:

    def test_load_returns_mission(self, mission):
        assert mission is not None

    def test_entity_count(self, mission):
        assert len(mission.entities) == 390

    def test_player_count(self, mission):
        assert len(mission.players) == 5

    def test_kill_count(self, mission):
        kills = mission.kills
        assert 80 <= len(kills) <= 100

    def test_hit_count(self, mission):
        hits = mission.hits
        assert 600 <= len(hits) <= 750

    def test_general_event_count(self, mission):
        gen = [e for e in mission.events if isinstance(e, GeneralEvent)]
        assert len(gen) >= 2

    def test_times_populated(self, mission):
        assert len(mission.times) > 0
        assert mission.times[0].frame_num == 0

    def test_times_last_frame(self, mission):
        assert mission.times[-1].frame_num == mission.end_frame

    def test_markers_populated(self, mission):
        assert len(mission.markers) > 0


class TestLoaderMetadata:

    def test_mission_name(self, mission):
        assert mission.mission_name == "Random Patrol Generator"

    def test_world_name(self, mission):
        assert mission.world_name == "zargabad"

    def test_end_frame(self, mission):
        assert mission.end_frame == 525

    def test_capture_delay(self, mission):
        assert mission.capture_delay == 3.0

    def test_addon_version(self, mission):
        assert mission.addon_version == "2.0.0"


class TestLoaderVehicles:

    def test_vehicle_classes(self, mission):
        vehicles = [e for e in mission.entities.values() if isinstance(e, VehicleEntity)]
        classes = {v.vehicle_class for v in vehicles}
        assert "tank" in classes
        assert "apc" in classes
        assert "car" in classes
        assert "static-weapon" in classes


class TestExportArtifacts:
    """Tests that generate data files in test_output/."""

    def test_export_mission_summary(self, mission, output_dir):
        summary = {
            "mission_name": mission.mission_name,
            "world_name": mission.world_name,
            "end_frame": mission.end_frame,
            "capture_delay": mission.capture_delay,
            "entity_count": len(mission.entities),
            "player_count": len(mission.players),
            "kill_count": len(mission.kills),
            "hit_count": len(mission.hits),
            "event_count": len(mission.events),
            "marker_count": len(mission.markers),
            "duration_seconds": mission.duration_seconds,
        }
        path = output_dir / "mission_summary.json"
        path.write_text(json.dumps(summary, indent=2))
        assert path.exists()
        loaded = json.loads(path.read_text())
        assert loaded["mission_name"] == "Random Patrol Generator"

    def test_export_player_stats(self, mission, output_dir):
        stats = []
        for p in mission.players:
            kills = mission.kills_by(p.id)
            deaths = mission.deaths_of(p.id)
            hits_dealt = [h for h in mission.hits if h.attacker_id == p.id]
            stats.append({
                "id": p.id,
                "name": p.name,
                "group": p.group,
                "role": p.role,
                "kills": len(kills),
                "deaths": len(deaths),
                "hits_dealt": len(hits_dealt),
                "shots_fired": p.total_shots,
                "death_frame": p.death_frame,
            })
        path = output_dir / "player_stats.json"
        path.write_text(json.dumps(stats, indent=2))
        assert path.exists()
        loaded = json.loads(path.read_text())
        assert len(loaded) == 5

    def test_export_kill_feed(self, mission, output_dir):
        feed = []
        for k in mission.kills:
            attacker = mission.get_entity(k.attacker_id)
            victim = mission.get_entity(k.victim_id)
            feed.append({
                "frame": k.frame,
                "attacker_id": k.attacker_id,
                "attacker_name": attacker.name if attacker else f"#{k.attacker_id}",
                "victim_id": k.victim_id,
                "victim_name": victim.name if victim else f"#{k.victim_id}",
                "weapon": k.weapon,
                "distance": k.distance,
            })
        path = output_dir / "kill_feed.json"
        path.write_text(json.dumps(feed, indent=2))
        assert path.exists()
        loaded = json.loads(path.read_text())
        assert len(loaded) > 0
        assert "weapon" in loaded[0]
