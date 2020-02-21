from datetime import date, datetime
import os
import numpy as np
import pandas as pd
from . import conf
from .utils import parse_period


class Ticker:
    """Manage ticker date and calculate descriptive statistics

    :param str ticker: Abbreviation for stock to load
    """

    def __init__(self, ticker):
        csv_path = os.path.join(conf['paths']['save'], f'{ticker.lower()}.csv')
        if isinstance(ticker, str) and os.path.isfile(csv_path):
            self.data = pd.read_csv(csv_path, parse_dates=['date'])
        else:
            raise ValueError(f'Ticker CSV not found at {csv_path}')
        self._format_csv()

    def _format_csv(self):
        """Shared between constructor methods to parse date column and add as index"""
        self.data.sort_values('date', inplace=True)
        self.data.set_index(pd.DatetimeIndex(self.data.date), inplace=True)

    def nearest(self, target_date):
        """Determine closest available business date to the target

        :param np.datetime64 or str target_date: Timestamp to use for indexing. Can
            be a preformatted NumPy object or plain string in yyyy-mm-dd format
        :return np.datetime64:
        """
        if isinstance(target_date, str):
            target_date = pd.Timestamp(datetime.strptime(target_date, '%Y-%m-%d')).to_numpy()
        if target_date in self.data.date.values:
            return target_date
        else:
            idx = self.data.index.get_loc(target_date, method='nearest')
            return self.data.iloc[idx].date.to_numpy()

    def price(self, date, exact=False):
        """Retrieve price by date from data attribute

        :param np.datetime64 or str date: Timestamp to use for indexing. Can
            be a preformatted NumPy object or plain string in yyyy-mm-dd format
        :param bool exact: Whether to require an exact timestamp match or use
            the closest date if the requested one is missing (due to date, non-
            business day, etc). If ``True`` a ``ValueError`` will be raised for
            unavailable dates
        :return float: Price on the requested date
        """
        if isinstance(date, str):
            date = pd.Timestamp(datetime.strptime(date, '%Y-%m-%d')).to_numpy()
        if date not in self.data.index:
            if not exact:
                date = self.nearest(date)
            else:
                raise ValueError(f'Start reference date {date} not in data')
        return self.data.loc[date].price

    def rolling(self, period, average=True):
        """Calculate rolling return of price data

        :param int or str period: Number of days for the return window or a
            keyword string such as daily, monthly, yearly, 5-year, etc.
        :param bool average: Whether to take the mean rolling return or
            return all individual datapoints
        :return float or pd.Series: Rolling return(s)
        """

        days = parse_period(period)
        rolling = self.data.price.pct_change(days).dropna()
        if average:
            return rolling.mean()
        else:
            return rolling

    def trailing(self, period, end='today'):
        """Calculate trailing return of price data

        :param int or str period: Number of days for the return window or a
            keyword string such as daily, monthly, yearly, 5-year, etc.
        :param str end: End date for point to point calculation. Either
            keyword ``today`` or a timestamp formatted ``yyyy-mm-dd``
        :return float:
        """
        days = parse_period(period)
        if end == 'today':
            end_dt = pd.Timestamp(date.today()).to_numpy()
        else:
            end_dt = pd.Timestamp(datetime.strptime(end, '%Y-%m-%d')).to_numpy()
        trail_dt = end_dt - np.timedelta64(days, 'D')
        end_price = self.price(end_dt)
        trail_price = self.price(trail_dt)
        return (end_price - trail_price) / trail_price

    @classmethod
    def from_df(self, dataframe):
        """Construct instance from pre-loaded data already in memory"""
        self.data = dataframe
        self._format_csv()
