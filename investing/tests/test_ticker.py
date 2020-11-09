from datetime import datetime
import unittest
from . import get_dummy_data
from investing.data import Ticker


class TestTicker(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.ticker = Ticker('dummy')
        cls.ticker.data = get_dummy_data(num_days=31, low=10, high=160)

    def test_trailing(self):
        """Test trailing returns for different periods"""
        end_str = datetime.strftime(self.ticker.data.index.max().to_pydatetime(), '%Y-%m-%d')
        day = self.ticker.metric('trailing/6-day', end=end_str)
        week = self.ticker.metric('trailing/2-week', end=end_str)
        month = self.ticker.metric('trailing/1-month', end=end_str)
        self.assertEqual(day, 30/130)
        self.assertEqual(week, 70/90)
        self.assertEqual(month, 150/10)


if __name__ == '__main__':

    unittest.main()
