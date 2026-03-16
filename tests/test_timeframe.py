from datetime import datetime

from models.timeframe import TimeFrame


class TestTimeFrame:

    def test_from_dict(self):
        d = {
            "date": "2026-03-09T12:30:00",
            "frameNum": 10,
            "systemTimeUTC": "2026-03-08T13:06:11.171",
            "time": 1100.85,
            "timeMultiplier": 2.0,
        }
        tf = TimeFrame.from_dict(d)
        assert tf.date == "2026-03-09T12:30:00"
        assert tf.frame_num == 10
        assert tf.system_time_utc == "2026-03-08T13:06:11.171"
        assert tf.time == 1100.85
        assert tf.time_multiplier == 2.0

    def test_game_datetime(self):
        tf = TimeFrame(
            date="2026-03-09T12:30:00",
            frame_num=0,
            system_time_utc="2026-03-08T13:00:00",
            time=0,
            time_multiplier=1.0,
        )
        dt = tf.game_datetime
        assert isinstance(dt, datetime)
        assert dt.year == 2026
        assert dt.month == 3
        assert dt.hour == 12
        assert dt.minute == 30

    def test_real_datetime(self):
        tf = TimeFrame(
            date="2026-03-09T12:30:00",
            frame_num=0,
            system_time_utc="2026-03-08T13:06:11.171",
            time=0,
            time_multiplier=1.0,
        )
        dt = tf.real_datetime
        assert isinstance(dt, datetime)
        assert dt.day == 8

    def test_real_data_times_sorted(self, mission):
        """Times should be in ascending frame order."""
        frame_nums = [t.frame_num for t in mission.times]
        assert frame_nums == sorted(frame_nums)
