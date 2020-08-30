"""
Ticker data is stored on disk at the location specified by
``config['paths']['save']`` with two columns (price and date). Data can be
loaded into Python and accessed via the `Ticker` class. This class has methods
to calculate descriptive statistics such as trailing and rolling returns of
differing time periods. Multiple `Ticker` objects can be combined into a
`Portfolio` object with optional weighting between the holdings.

The data module also contains several useful helper functions for parsing
common financial periods and querying valid market days.
"""

from datetime import date, datetime, timedelta
import os
from warnings import warn
import pandas as pd
import pandas_market_calendars as mcal
import pytz
import numpy as np
from . import conf
from .download import timeseries
from .exceptions import TickerDataError
from .mappings import ticker2name


def market_day(direction, reference='today', search_days=7):
    """Return the closest completed and valid market day

    If ``reference == 'today'``, the current time will be compared to the
    market's closing time. For future or past reference dates, it is assumed
    that the time of day referenced is after close.

    :param str direction: One of previous, latest, next
    :param str reference: Day to search relative to (yyyy-mm-dd format or
        ``'today'`` for the current day
    :param int search_days: Symmetrical number of days to check on either
        side of the provided ``reference``
    :return np.datetime64: Date stamp
    """

    # Load calendar and format datetime reference
    nyse = mcal.get_calendar('NYSE')
    if reference == 'today':
        ref_day = date.today()
    else:
        ref_day = datetime.strptime(reference, '%Y-%m-%d').date()

    # Build list of valid market days within window and determine closest index to reference
    search_window = timedelta(days=search_days)
    recent = nyse.valid_days(start_date=ref_day - search_window, end_date=ref_day + search_window)
    if len(recent) == 0:
        raise RuntimeError(f'No valid dates found within {search_days} days, try expanding window')
    diffs = pd.DataFrame(recent - pd.Timestamp(ref_day, tz='UTC'))
    idx = diffs[diffs <= timedelta(days=0)].idxmax()

    # Check whether market has closed if latest valid date is today
    latest_valid = recent[idx][0].to_numpy()
    closing_time = nyse.schedule(start_date=latest_valid, end_date=latest_valid).market_close[0]
    now = datetime.now(tz=pytz.timezone(conf['locale']))
    if closing_time.date() == now.date() and closing_time > now:
        idx -= 1

    # Adjust returned date by requested direction
    assert direction in ['previous', 'latest', 'next'], f'Invalid direction {direction}'
    if direction == 'previous':
        idx -= 1
    elif direction == 'next':
        idx += 1
    return recent[idx][0].to_numpy()


def parse_period(period):
    """Convert various financial periods to number of days

    :param int/str period: Number of days for the return window or one of
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
        elif len(weights) != len(tickers):
            raise ValueError(f'Mismatch between number of tickers ({len(tickers)}) and weights ({len(weights)})')
        elif sum(weights) != 1.0:
            raise ValueError(f'Weights must sum to 1 (got {sum(weights)} instead)')
        else:
            self.weights = weights
        self.holdings = [Ticker(t) for t in tickers]

    def __str__(self):
        """Human readable naming for all holdings"""
        return ', '.join([f'{h.symbol} ({w:.2f})' for h, w in zip(self.holdings, self.weights)])

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
        sample_pools = [h.metric(f'rolling/{period}', average=False) for h in self.holdings]
        missing = [len(s) == 0 for s in sample_pools]
        if any(missing):
            too_long = ', '.join([self.holdings[i].symbol for i, m in enumerate(missing) if m])
            raise RuntimeError(f'Insufficient data for {period} period for holdings {too_long}')
        individual = np.stack([s.sample(n, replace=True).values for s in sample_pools])
        composite = np.sum(individual * np.array(self.weights).reshape((-1, 1)), axis=0)
        return composite.mean(), composite.std(), min(len(s) for s in sample_pools)

    @property
    def name(self):
        """Human readable naming for all holdings via call to internal __str__"""
        return str(self)


class Ticker:
    """Manages ticker data and calculates descriptive statistics

    Price data is stored on disk in a CSV and loaded into the ``data``
    attribute as a Pandas ``DataFrame``. Prices are indexed by date in
    descending order (most recent first).

    The free-tier of Alpha-Vantage limits users to 5 API calls/minute.
    Therefore, the ``data`` attribute is only refreshed on explicit calls.
    Auto-refreshing on each initialization might exceed the rate limit if the
    calling scope creates several ``Ticker`` objects simultaneously.
    """

    def __init__(self, symbol):
        """Load data from disk and format in Pandas

        :param str symbol: Case-insensitive stock abbreviation
        """

        self.symbol = symbol.upper()
        self.csv_path = os.path.join(conf['paths']['save'], f'{symbol.lower()}.csv')
        if os.path.isfile(self.csv_path):
            self.data = pd.read_csv(self.csv_path, parse_dates=['date'], index_col=['date'])
        else:
            self.data = pd.DataFrame(columns=['price'])
        self._sort_dates()

    def __str__(self):
        """Full company name"""
        return ticker2name.get(self.symbol.upper(), 'Unknown')

    def __repr__(self):
        """Displayable instance name for print() function"""
        return f'Ticker({self.symbol})'

    def _nearest(self, target_date):
        """Determine closest available business date to the target

        :param np.datetime64 or str target_date: Timestamp to use for indexing. Can
            be a preformatted NumPy object or plain string in yyyy-mm-dd format
        :return np.datetime64:
        """
        if isinstance(target_date, str):
            target_date = pd.Timestamp(datetime.strptime(target_date, '%Y-%m-%d')).to_numpy()
        if target_date in self.data.index.values:
            return target_date
        else:
            if target_date > self.data.index.max():
                warn('Target date exceeds max downloaded')
            idx = self.data.index.get_loc(target_date, method='nearest')
            return self.data.iloc[idx].date.to_numpy()

    def _rolling(self, days, average=True):
        """Calculate rolling return of price data

        :param int or str days: Number of days for the return window
        :param bool average: Whether to take the mean rolling return or
            return all individual datapoints
        :return float or pd.Series: Rolling return(s)
        """

        rolling = self.data.price.pct_change(days).dropna()
        if average:
            return rolling.mean()
        else:
            return rolling

    def _sort_dates(self):
        """Place most recent dates at top

        Order is assumed by some metrics like ``_rolling``, so we need to
        share this between the constructor and refresh methods for consistency
        """
        self.data.sort_index(ascending=False, inplace=True)

    def _trailing(self, days, end='today'):
        """Calculate trailing return of price data

        :param int or str days: Number of days for the return window
        :param str end: End date for point to point calculation. Either
            keyword ``today`` or a timestamp formatted ``yyyy-mm-dd``
        :return float:
        """
        if end == 'today':
            end_dt = pd.Timestamp(date.today()).to_numpy()
        else:
            end_dt = pd.Timestamp(datetime.strptime(end, '%Y-%m-%d')).to_numpy()
        trail_dt = end_dt - np.timedelta64(days, 'D')
        end_price = self.price(end_dt)
        trail_price = self.price(trail_dt)
        return (end_price - trail_price) / trail_price

    @property
    def has_csv(self):
        """Check whether correspond CSV exists on disk"""
        return os.path.isfile(self.csv_path)

    @property
    def is_current(self):
        """Check if instance has the most recent ticker data

        :return bool: Whether the latest timestamp matches the last market day
        """
        if len(self.data) == 0:
            return False
        latest_close = market_day('latest')
        return latest_close <= self.data.index.max()

    def metric(self, metric_name, **kwargs):
        """Parse metric names and dispatch to appropriate internal method

        :param str metric_name: In the form ``metric_type/period`` where
            ``metric_type`` is rolling, trailing, etc and ``period`` is a
            financial period interpretable by ``parse_period``
        :param dict kwargs: Metric-specifc arguments to be forwarded
        :return float: Calculated metric
        :raises NotImplementedError: For metric names with no corresponding
            class method
        """
        if len(self.data) == 0:
            raise TickerDataError('No data available, try running .refresh()')
        try:
            metric_type, period = metric_name.split('/')
        except ValueError:
            raise ValueError(f'Metric {metric_name} does not match metric_type/period format')
        try:
            method = getattr(self, '_' + metric_type)
        except AttributeError:
            raise NotImplementedError(f'No metric defined for {metric_type}')
        return method(parse_period(period), **kwargs)

    @property
    def name(self):
        """Full company name via call to internal __str__"""
        return str(self)

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
                date = self._nearest(date)
            else:
                raise ValueError(f'Requested date {date} not in data')
        return self.data.loc[date].price

    def refresh(self):
        """Refresh local ticker data

        Idempotent behavior if data is already current
        """

        # Check status of existing data
        if self.is_current:
            return
        if self.has_csv:
            if self.data.index.max() < datetime.today() - timedelta(days=100):
                length = 'full'
            else:
                length = 'compact'
            existing = self.data
        else:
            length = 'full'
            existing = None

        # Merge data from Alpha-Vantage API with existing and write to disk
        new = timeseries(self.symbol, length)
        if existing is not None:
            combined = pd.concat([new, existing])
            self.data = combined[~combined.index.duplicated()]
        else:
            self.data = new
        self._sort_dates()
        self.data.to_csv(self.csv_path)
