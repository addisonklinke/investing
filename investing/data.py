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

from collections import defaultdict
from datetime import date, datetime, timedelta
from dateutil.relativedelta import relativedelta
import os
import re
from warnings import warn
import pandas as pd
import pandas_market_calendars as mcal
import pytz
import numpy as np
from . import conf
from .download import Holdings, metals, timeseries
from .exceptions import TickerDataError
from .mappings import forex, ticker2name

# TODO handle pricing for stock splits


def annualize(total_return, period):
    """Convert raw returns over time period to compounded annual rate

    :param float total_return: Raw return
    :param str/int period: Financial period interpretable by ``parse_period``
    :return float:
    """
    years = parse_period(period) / 365
    return (1 + total_return) ** (1/years) - 1


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
        the following keyword strings. Each keyword can be adjusted using a
        dash and modifier (i.e. 2-day, 6-year, etc)
            * day
            * month
            * quarter
            * year
            * ytd
    :return int days:
    """
    if isinstance(period, int):
        days = period
    elif isinstance(period, str):
        today = datetime.today()
        keyword_durations = {
            'day': 1,
            'week': 7,
            'month': 30,
            'quarter': 91,
            'year': 365,
            'ytd': (today - datetime(today.year, 1, 1)).days}
        if '-' in period:
            multiplier, keyword = period.split('-')
            multiplier = int(multiplier)
        else:
            keyword = period
            multiplier = 1
        if keyword not in keyword_durations:
            raise ValueError(f'{period} string does not match supported formats')
        days = multiplier * keyword_durations[keyword]
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
        self.tickers = [Ticker(t) for t in tickers]
        self._company_positions = None

    def __str__(self):
        """Human readable naming for all holdings"""
        return ', '.join([f'{t.symbol}={w:.2f}' for t, w in zip(self.tickers, self.weights)])

    def __repr__(self):
        """Displayable instance name for print() function"""
        return f'Portfolio[{str(self)}]'

    @property
    def company_positions(self):
        """Expand any ETFs into their constituent holdings

        Cache the structure as a private attribute since it can be rather large
        and slow to compute for multiple ETFs

        :return dict positions: Where keys are company-level tickers and values
        are lists of dictionaries containing the source ticker (either the company
        itself or the ETF holding it) and the company's weight within the source
        and portfolio as a whole. For example

            {
                'AAPL': [
                    {
                        'source': 'VTI',
                        'source_weight': 0.04,
                        'portfolio_weight': 0.02,
                    },
                    {
                        'source': 'VGT',
                        'source_weight': 0.12,
                        'portfolio_weight': 0.05,
                    }
                ],
                'AMZN': [
                    {
                        'source': 'AMZN',
                        'source_weight': 1.0,
                        'portfolio_weight': 0.23,
                    }
                ]
            }
        """
        if self._company_positions is None:
            self._company_positions = defaultdict(list)
            for ticker, weight in zip(self.tickers, self.weights):
                symbol = ticker.symbol.upper()
                if ticker.holdings is None:
                    self._company_positions[symbol].append({
                        'source': symbol,
                        'source_weight': 1,
                        'portfolio_weight': weight})
                else:
                    for i, row in ticker.holdings.iterrows():
                        self._company_positions[row.symbol].append({
                            'source': symbol,
                            'source_weight': row.pct,
                            'portfolio_weight': row.pct * weight})
        return self._company_positions

    def expected_return(self, period, n=1000):
        """Monte-Carlo simulation of typical return and standard deviation

        :param int or str period: Number of days for the return window or a
            keyword string such as daily, monthly, yearly, 5-year, etc.
        :param int n: Number of simulations to run
        :return 3-tuple(float): Mean and standard deviation of return and
            least number of data points used for an individual holding
        """
        sample_pools = [t.metric(f'rolling/{period}', average=False) for t in self.tickers]
        missing = [len(s) == 0 for s in sample_pools]
        if any(missing):
            too_long = ', '.join([self.tickers[i].symbol for i, m in enumerate(missing) if m])
            raise RuntimeError(f'Insufficient data for {period} period for holdings {too_long}')
        individual = np.stack([s.sample(n, replace=True).values for s in sample_pools])
        composite = np.sum(individual * np.array(self.weights).reshape((-1, 1)), axis=0)
        return composite.mean(), composite.std(), min(len(s) for s in sample_pools)

    def exposure(self, symbol):
        """Weight of a specific company within the portfolio

        :param str symbol: Case insensitive ticker
        :return float: Total weight across the portfolio
        """
        symbol = symbol.upper()
        if symbol not in self.company_positions:
            raise KeyError(f'{symbol} not found in company positions')
        return sum(s['portfolio_weight'] for s in self.company_positions[symbol])

    def max_exposure(self, limit=10):
        """Top N companies across portfolio

        :param int limit: Maximum number of companies to return
        :return List[Tuple] exposures: Symbol of total portfolio weight
        """
        exposures = [(symbol, self.exposure(symbol)) for symbol in self.company_positions]
        exposures = sorted(exposures, key=lambda tup: tup[1], reverse=True)
        return exposures[:limit]

    @property
    def name(self):
        """Human readable naming for all holdings via call to internal __str__"""
        return str(self)

    def duplicate_positions(self, thres=0.01):
        """Determine any companies shared across ETFs

        :param float thres: Minimum percent of the company within ETF to count as
            a duplicate. For instance, AAPL is 21% of VGT and 5.8% of VTI, so under
            the default threshold it would be flagged as a duplicate. However, MU
            is only 0.77% of VGT and 0.22% of VTI so it would not be flagged
        :return dict duplicates: Following the same structure as ``self.company_positions``
        """
        duplicates = {}
        for company, sources in self.company_positions.items():
            held_by = {s['source'] for s in sources}
            if len(held_by) == 1:
                continue
            percents = [s['source_weight'] for s in sources]
            if any(percent >= thres for percent in percents):
                duplicates.update({company: sources})
        return duplicates


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

    def __init__(self, symbol, merge=None):
        """Load data from disk and format in Pandas

        :param str symbol: Case-insensitive stock abbreviation
        :param str merge: Add a ``relative`` column for price compared to
            another ticker (i.e. XAU for gold oz) for any overlapping dates.
        """

        self.symbol = symbol.upper()

        # The primary ticker timeseries
        self.csv_path = os.path.join(conf['paths']['save'], f'{symbol.lower()}.csv')
        if os.path.isfile(self.csv_path):
            self.data = pd.read_csv(
                self.csv_path,
                converters={'price': self._force_float},
                parse_dates=['date'],
                index_col=['date'])
            if merge is not None:
                relative_csv = os.path.join(conf['paths']['save'], f'{merge}.csv')
                if os.path.isfile(relative_csv):
                    rel = pd.read_csv(
                        relative_csv,
                        converters={'price': self._force_float},
                        parse_dates=['date'],
                        index_col=['date'])
                    rel.rename(columns={'price': 'other'}, inplace=True)
                    combined = self.data.join(rel)
                    self.data['relative'] = combined.apply(lambda row: row.price / row.other, axis=1)
        else:
            self.data = pd.DataFrame(columns=['price'])
        self._sort_dates()

        # Holdings (if an ETF or other combined fund)
        self.holdings_path = os.path.join(conf['paths']['save'], f'{symbol.lower()}.holdings.csv')
        if os.path.isfile(self.holdings_path):
            self.holdings = pd.read_csv(self.holdings_path, keep_default_na=False)  # In case of "NA" ticker
        else:
            self.holdings = None

    def __str__(self):
        """Full company name"""
        return ticker2name.get(self.symbol.upper(), 'Unknown')

    def __repr__(self):
        """Displayable instance name for print() function"""
        return f'Ticker({self.symbol})'

    @staticmethod
    def _force_float(raw):
        """Cast various data types to float"""
        if isinstance(raw, float):
            return raw
        elif isinstance(raw, int):
            return float(raw)
        elif isinstance(raw, str):
            clean = re.sub('[^0-9\.]+', '', raw)
            return float(clean)
        else:
            raise NotImplementedError(f'Unsure how to cast {raw} of type {type(raw)}')

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
            return self.data.index[idx].to_numpy()

    def _rolling(self, period, average=True):
        """Calculate rolling return of price data

        Pandas ``pct_change`` returns the percent difference in descending
        order, i.e. ``(data[idx + n] - data[idx]) / data[idx]`` so values at
        higher indices must increase in order for the change to be positive

        :param str period: Number of days for the return window
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

    def _sort_dates(self):
        """Place most recent dates at bottom

        Order is assumed by some metrics like ``_rolling``, so we need to
        share this between the constructor and refresh methods for consistency
        """
        self.data.sort_index(inplace=True)

    def _trailing(self, period, end='today'):
        """Calculate trailing return of price data

        :param str period: Number of days for the return window
        :param str end: End date for point to point calculation. Either
            keyword ``today`` or a timestamp formatted ``yyyy-mm-dd``
        :return float:
        """

        # Setup end date
        if end == 'today':
            end_dt = date.today()
        else:
            end_dt = datetime.strptime(end, '%Y-%m-%d')

        # Calculate trailing date
        if '-' in period:
            multiplier, keyword = period.split('-')
            multiplier = int(multiplier)
        else:
            keyword = period
            multiplier = 1
        if keyword in ['day', 'month', 'year']:
            trail_dt = end_dt - relativedelta(**{keyword + 's': multiplier})
        else:
            trail_dt = end_dt - timedelta(days=parse_period(period))

        # Convert to NumPy format to extract prices from index
        end_price = self.price(pd.Timestamp(end_dt).to_numpy())
        trail_price = self.price(pd.Timestamp(trail_dt).to_numpy())
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

        :param str metric_name: 2-3 part string separated by forward slashes
            1) metric_type: matching an implemented internal method (i.e.
                rolling, trailing, etc)
            2) period: a financial period interpretable by ``parse_period``
            3) options: one or more compatible key-letter flags
                * a: annualized
        :param dict kwargs: Metric-specifc arguments to be forwarded
        :return float: Calculated metric
        :raises NotImplementedError: For metric names with no corresponding
            class method
        """
        if len(self.data) == 0:
            raise TickerDataError(f'No data available for {self.symbol}, try running .refresh()')
        try:
            metric_type, period, *options = metric_name.split('/')
        except ValueError:
            raise ValueError(f'Metric {metric_name} does not match metric_type/period/options format')
        try:
            method = getattr(self, '_' + metric_type)
        except AttributeError:
            raise NotImplementedError(f'No metric defined for {metric_type}')
        result = method(period, **kwargs)
        if len(options) > 0:
            if 'a' in options:
                result = annualize(result, period)
            else:
                warn(f'Ignoring unknown metric option(s) {options}')
        return result

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

    def refresh(self, holdings=False):
        """Refresh local ticker data

        Idempotent behavior if data is already current

        :param bool holdings: Whether or not to attempt refreshing the fund holdings
        :return None: Updates the ``self.data`` attribute and merges CSV data on disk
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

        # Merge data from Alpha-Vantage or Metals API with existing and write to disk
        if self.symbol in forex:
            new = metals(self.symbol)
        else:
            new = timeseries(self.symbol, length)
        if existing is not None:
            combined = pd.concat([new, existing])
            combined = combined[~combined.index.duplicated()]
            self.data = combined
        else:
            self.data = new
        self._sort_dates()
        self.data.to_csv(self.csv_path)

        # Update holdings
        if holdings:
            latest = Holdings(self.symbol).download()
            latest.to_csv(self.holdings_path, index=False)
            self.holdings = latest
