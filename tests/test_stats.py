import pytest
from utils.stats import Stats, INTERVAL_DESERTED, INTERVAL_MEDIUM, INTERVAL_HIGHEST, INTERVAL_LOW


class TestStats:
    @staticmethod
    def interval_test_data():
        """Yields subscriber, posts_per_day, expected"""
        return [
            (10, 0, INTERVAL_DESERTED),
            (1, 1, INTERVAL_DESERTED),
            (1, 100, INTERVAL_DESERTED),
            (100, 3, INTERVAL_LOW),
            (2, 130, INTERVAL_LOW),
            (11, 10, INTERVAL_MEDIUM),
            (13, 41, INTERVAL_MEDIUM),
            (50, 41, INTERVAL_HIGHEST),
        ]

    @pytest.mark.parametrize("subscribers, posts_per_day, expected", interval_test_data())
    def test_decide_interval(self, subscribers, posts_per_day, expected):
        result = Stats.decide_interval(subscribers, posts_per_day)
        assert result == expected
