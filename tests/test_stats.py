import pytest
from utils.stats import Stats, INTERVAL_BI_DAILY, INTERVAL_MEDIUM, INTERVAL_HIGHEST, INTERVAL_LOW, INTERVAL_DESERTED


class TestStats:
    @staticmethod
    def interval_test_data():
        """Yields subscriber, posts_per_day, expected"""
        return [
            (1, 1, INTERVAL_DESERTED),
            (10, 0, INTERVAL_BI_DAILY),
            (2, 100, INTERVAL_BI_DAILY),
            (100, 3, INTERVAL_LOW),
            (5, 130, INTERVAL_LOW),
            (11, 10, INTERVAL_MEDIUM),
            (13, 41, INTERVAL_MEDIUM),
            (50, 41, INTERVAL_HIGHEST),
        ]

    @pytest.mark.parametrize("subscribers, posts_per_day, expected", interval_test_data())
    def test_decide_interval(self, subscribers, posts_per_day, expected):
        result = Stats.decide_interval(subscribers, posts_per_day)
        assert result == expected
