from aar_pipeline.models.event import Event, HitEvent, KillEvent, GeneralEvent, ConnectionEvent


class TestEventFactory:

    def test_hit_event(self):
        raw = [36, "hit", 82, [238, "HK416D [M855]"], 13]
        ev = Event.from_raw(raw)
        assert isinstance(ev, HitEvent)
        assert ev.frame == 36
        assert ev.event_type == "hit"
        assert ev.victim_id == 82
        assert ev.attacker_id == 238
        assert ev.weapon == "HK416D [M855]"
        assert ev.distance == 13

    def test_kill_event(self):
        raw = [2, "killed", 65, [241, "Seekins SP-10M [6.5 Creedmoor]"], 827]
        ev = Event.from_raw(raw)
        assert isinstance(ev, KillEvent)
        assert ev.frame == 2
        assert ev.victim_id == 65
        assert ev.attacker_id == 241
        assert ev.weapon == "Seekins SP-10M [6.5 Creedmoor]"
        assert ev.distance == 827

    def test_general_event(self):
        raw = [0, "generalEvent", "Mission has started!"]
        ev = Event.from_raw(raw)
        assert isinstance(ev, GeneralEvent)
        assert ev.message == "Mission has started!"
        assert ev.frame == 0

    def test_connection_event_connected(self):
        raw = [10, "connected", 5]
        ev = Event.from_raw(raw)
        assert isinstance(ev, ConnectionEvent)
        assert ev.event_type == "connected"
        assert ev.player_id == 5

    def test_connection_event_disconnected(self):
        raw = [50, "disconnected", 3]
        ev = Event.from_raw(raw)
        assert isinstance(ev, ConnectionEvent)
        assert ev.event_type == "disconnected"

    def test_unknown_event_type(self):
        raw = [99, "someNewType"]
        ev = Event.from_raw(raw)
        assert type(ev) is Event
        assert ev.event_type == "someNewType"

    def test_hit_attacker_not_list(self):
        raw = [10, "hit", 5, 99, 50]
        ev = Event.from_raw(raw)
        assert isinstance(ev, HitEvent)
        assert ev.attacker_id == 99
        assert ev.weapon == ""


class TestEventRealData:

    def test_all_events_have_frame(self, mission):
        for ev in mission.events:
            assert isinstance(ev.frame, int)
            assert ev.frame >= 0

    def test_kill_events_have_weapon(self, mission):
        for k in mission.kills:
            assert isinstance(k.weapon, str)
