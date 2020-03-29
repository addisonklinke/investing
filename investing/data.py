from datetime import date, datetime
import os
import numpy as np
import pandas as pd
from . import conf
from .mappings import ticker2name


def parse_period(period):
    """Convert various financial periods to number of days

    :param int or str period: Number of days for the return window or one of
        the following keyword strings
            * daily
            * monthly
            * quarterly
            * yearly
            * n-year
    :return int days:
    """
    if isinstance(period, int):
        days = period
    elif isinstance(period, str):
        if period == 'daily':
            days = 1
        elif period == 'monthly':
            days = 30
        elif period == 'quarterly':
            days = 91
        elif period == 'yearly':
            days = 365
        elif period.endswith('year') and '-' in period:
            days = int(period.split('-')[0]) * 365
        else:
            raise ValueError(f'{period} string does not match supported formats')
    else:
        raise ValueError(f'Exepcted type int or str, but received {type(period)}')
    return days


class Portfolio:
    """Combination of several holdings

    :param [str] tickers: Iterable list of case-insensitive stock abbreviations
    :param [float] weights: Percent of portfolio each stock makes up (leave as
        ``None`` for even splits)
    """

    def __init__(self, tickers, weights=None):
        if weights is None:
            self.weights = [1/len(tickers)] * len(tickers)
        elif len(self.weights) != len(tickers):
            raise ValueError(f'Mismatch between number of tickers ({len(tickers)}) and weights ({len(weights)})')
        elif sum(weights) != 1.0:
            raise ValueError(f'Weights must sum to 1 (got {sum(weights)} instead)')
        else:
            self.weights = weights
        self.holdings = [Ticker(t) for t in tickers]

    def __str__(self):
        """Human readable naming for all holdings"""
        return ', '.join([f'{h.ticker} ({w:.2f})' for h, w in zip(self.holdings, self.weights)])

    def __repr__(self):
        """Displayable instance name for print() function"""
        return f'Portfolio[{str(self)}]'

    def expected_return(self, period, n=1000):
        """Monte-Carlo simulation of typical return and standard deviation

        :param int or str period: Number of days for the return window or a
            keyword string such as daily, monthly, yearly, 5-year, etc.
        :param int n: Number of simulations to run
        :return 3-tuple(float): Mean and standard deviation of return and
            least number of data points used for an individual holding
        """
        sample_pools = [h.rolling(period, average=False) for h in self.holdings]
        missing = [len(s) == 0 for s in sample_pools]
        if any(missing):
            too_long = ', '.join([self.holdings[i].ticker for i, m in enumerate(missing) if m])
            raise RuntimeError(f'Insufficient data for {period} period for holdings {too_long}')
        individual = np.stack([s.sample(n, replace=True).values for s in sample_pools])
        composite = np.sum(individual * np.array(self.weights).reshape((-1, 1)), axis=0)
        return composite.mean(), composite.std(), min(len(s) for s in sample_pools)

    @property
    def name(self):
        """Human readable naming for all holdings via call to internal __str__"""
        return str(self)


class Ticker:
    """Manage ticker data and calculate descriptive statistics

    :param str ticker: Case-insensitive stock abbreviation
    """

    def __init__(self, ticker):
        self.ticker = ticker.upper()
        csv_path = os.path.join(conf['paths']['save'], f'{ticker.lower()}.csv')
        if isinstance(ticker, str) and os.path.isfile(csv_path):
            self.data = pd.read_csv(csv_path, parse_dates=['date'])
        else:
            raise ValueError(f'Ticker CSV not found at {csv_path}')
        self._format_csv()

    def __str__(self):
        """Full company name"""
        return ticker2name.get(self.ticker.upper(), 'Unknown')

    def __repr__(self):
        """Displayable instance name for print() function"""
        return f'Ticker({self.ticker})'

    def _format_csv(self):
        """Shared between constructor methods to parse date column and add as index"""
        self.data.sort_values('date', inplace=True)
        self.data.set_index(pd.DatetimeIndex(self.data.date), inplace=True)

    def metric(self, metric_name):
        """Parse metric names and dispatch to appropriate method

        :param str metric_name: In the form ``{rolling,trailing}/period``
        :return float: Calculated metric
        :raises ValueError: For improperly formatted metric names
        """
        try:
            metric_type, period = metric_name.split('/')
        except ValueError:
            raise ValueError(f'Metric {metric_name} does not match {{rolling,trailing}}/period format')
        if metric_type == 'rolling':
            return self.rolling(period)
        elif metric_type == 'trailing':
            return self.trailing(period)
        else:
            raise ValueError(f'Expected metric type to be rolling or trailing, but received {metric_type}')

    @property
    def name(self):
        """Full company name via call to internal __str__"""
        return str(self)

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