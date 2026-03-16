from models.event import KillEvent, HitEvent
from models.entity import Entity


EXPECTED_PLAYER_NAMES = {
    "1LT Canny", "2d Lt Alan", "1st Lt C. K. Felix", "SSG Alex", "MSgt Tin T."
}


class TestMissionPlayers:

    def test_player_count(self, mission):
        assert len(mission.players) == 5

    def test_player_names(self, mission):
        names = {p.name for p in mission.players}
        assert names == EXPECTED_PLAYER_NAMES

    def test_all_players_flagged(self, mission):
        for p in mission.players:
            assert p.is_player is True


class TestMissionGetEntity:

    def test_known_id(self, mission):
        e = mission.get_entity(0)
        assert e is not None
        assert isinstance(e, Entity)
        assert e.id == 0

    def test_unknown_id(self, mission):
        assert mission.get_entity(999999) is None


class TestMissionEvents:

    def test_kills_type(self, mission):
        kills = mission.kills
        assert len(kills) > 50
        for k in kills:
            assert isinstance(k, KillEvent)

    def test_hits_type(self, mission):
        hits = mission.hits
        assert len(hits) > 100
        for h in hits[:50]:
            assert isinstance(h, HitEvent)

    def test_kills_by_player(self, mission):
        """At least one player should have kills."""
        any_kills = False
        for p in mission.players:
            if len(mission.kills_by(p.id)) > 0:
                any_kills = True
                break
        assert any_kills

    def test_deaths_of(self, mission):
        """Some entities should have been killed."""
        kill = mission.kills[0]
        deaths = mission.deaths_of(kill.victim_id)
        assert len(deaths) >= 1

    def test_events_for_entity(self, mission):
        """Entity involved in a kill should appear in events_for_entity."""
        kill = mission.kills[0]
        events = mission.events_for_entity(kill.attacker_id)
        assert len(events) > 0


class TestMissionTime:

    def test_frame_to_time(self, mission):
        tf = mission.frame_to_time(0)
        assert tf is not None
        assert tf.frame_num == 0

    def test_frame_to_time_mid(self, mission):
        tf = mission.frame_to_time(250)
        assert tf is not None
        assert tf.frame_num <= 250

    def test_duration_seconds(self, mission):
        assert mission.duration_seconds > 0

    def test_str(self, mission):
        s = str(mission)
        assert "Random Patrol Generator" in s
        assert "zargabad" in s
