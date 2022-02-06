"""Retrieve data from configured API endpoints"""

from datetime import datetime, timedelta
import json
import os
import re
import pandas as pd
import requests
from . import conf
from .exceptions import APIError
from .mappings import ticker2name
from .utils import paginate_selenium_table


def metals(ticker, base='USD', look_back=5):
    """Get precious metal prices relative to USD or other base currency

    See official documentation on Metals API website
    https://metals-api.com/documentation#timeseries

    :param str ticker: Case insensitive exchange symbol (i.e. XAU for gold)
    :param str base: Currency or metal code for calculating relative prices
    :param str/int look_back: Number of days to return (limited to 5 on free tier)
    :return pd.DataFrame:
    """

    # Setup date range (per support discussion ``end_date`` must be yesterday at most)
    end_date = datetime.today() - timedelta(days=1)
    start_date = end_date - timedelta(days=look_back)

    # Check endpoint status
    r = requests.get(
        url=conf['endpoints']['metals'],
        params={
            'access_key': conf['keys']['metals'],
            'base': base,
            'symbols': ticker,
            'start_date': start_date.strftime('%Y-%m-%d'),
            'end_date': end_date.strftime('%Y-%m-%d')})
    if not r.ok:
        raise APIError(f'Metals API bad status code {r.status_code} for {r.url}')

    # Parse exchange rates and format into Pandas
    data = json.loads(r.content)
    exchage_rates = {date: prices[base.upper()] / prices[ticker.upper()] for date, prices in data['rates'].items()}
    dates, prices = zip(*exchage_rates.items())
    df = pd.DataFrame({'price': prices}, index=pd.DatetimeIndex(dates))
    df.index.name = 'date'
    return df


def news(ticker=None):
    """Gather news articles for general market or a specific ticker.

    :param str ticker: Defaults to ``None`` for general market news.
    :return [dict] articles: List of JSON formatted news articles where each
        item includes the following keys
            * category (str)
            * datetime (int)
            * headline (str)
            * id (int)
            * image (str)
            * related (str)
            * source (str)
            * summary (str)
            * url (str)
    """
    url = conf['endpoints']['finnhub']['news']
    if ticker is None:
        params = {'category': 'general'}
    else:
        url = os.path.join(url, ticker.upper())
        params = {}
    params.update({'token': conf['keys']['finnhub']})
    r = requests.get(url, params)
    articles = json.loads(r.content)
    return articles


def sentiment(ticker):
    """Download sentiment score of company news articles

    :param str ticker: Case-insentive stock symbol
    :return float: 0-1 rating with 1 being bullish. None if no news articles
        were available
    """
    url = conf['endpoints']['finnhub']['sentiment']
    params = {
        'symbol': ticker,
        'token': conf['keys']['finnhub']}
    r = requests.get(url, params)
    data = json.loads(r.content)
    if not r.ok:
        raise APIError(f'Bad status code {r.status_code} from Finnhub sentiment')
    return data['companyNewsScore']


def timeseries(ticker, length='compact'):
    """Download stock prices from Alpha Vantage API.

    :param str ticker: Uppercase stock abbreviation.
    :param str length: Either compact (last 100 days) or full (20 years).
    :return pd.DataFrame df: One column for price plus ``pd.DateTimeIndex``
    """

    # Check endpoint status
    r = requests.get(
        url=conf['endpoints']['alpha_vantage'],
        params={
            'function': 'TIME_SERIES_DAILY',
            'symbol': ticker.upper(),
            'outputsize': length,
            'apikey': conf['keys']['alpha_vantage']})
    if not r.ok:
        raise APIError(f'AlphaVantage API bad status code {r.status_code}')

    # Parse closing prices
    try:
        data = json.loads(r.content)
        ts = {k: float(v['4. close']) for k, v in data['Time Series (Daily)'].items()}
    except KeyError:
        raise APIError(f'Alpha-Vantage data could not be found/loaded for ticker {ticker}')

    # Format into Pandas
    dates, prices = zip(*ts.items())
    df = pd.DataFrame({'price': prices}, index=pd.DatetimeIndex(dates))
    df.index.name = 'date'
    return df


class Holdings:
    """Dispatch to appropriate download function depending on issuer"""

    # TODO combine all types of data downloads (news, sentiment, etc) under a single class-based client
    # Then it could be an attribute the ``Ticker`` class uses to refresh

    def __init__(self, symbol):
        """Pull in name from mapping

        :param str symbol: Ticker symbol (case insensitive)
        """
        self.symbol = symbol.upper()
        self.name = ticker2name.get(self.symbol)

    def download(self, **kwargs):
        """Get weighted set of stock holdings for a particular fund/company

        :param kwargs: To pass on to individual methods
        :return pd.Dataframe df: With columns for
            * symbol: The uppercase ticker symbol
            * pct: Percent of portfolio (sorted highest first)
        """

        # Check common ETF issuers (i.e. Vanguard, iShares, etc)
        configured_issuers = ['vanguard']
        download_method = None
        if self.name is not None:
            for issuer in configured_issuers:
                if issuer in self.name.lower():
                    download_method = issuer
                    break

        # Otherwise the symbol may be a company listed on Dataroma
        if download_method is None:
            download_method = 'dataroma'

        # Execute the dispatch
        method = getattr(self, download_method, None)
        if method is None:
            raise NotImplementedError(f'Could not find download method Holdings.{download_method}()')
        df = method(**kwargs)
        if len(df) == 0:
            raise APIError(f'Empty table return for {self.symbol} from Holdings.{download_method}()')
        if df.columns.to_list() != ['symbol', 'pct']:
            raise AttributeError('Expected dataframe to have columns [symbol, pct]')
        df.sort_values('pct', ascending=False, inplace=True)
        df.reset_index(inplace=True, drop=True)
        return df

    def dataroma(self):
        """Used for individuals and companies who are required to file form 13F by the SEC"""

        # Download the table
        r = requests.get(conf['endpoints']['dataroma'], {'m': 'GFT'}, headers={"User-Agent": "XY"})
        try:
            tables = pd.read_html(r.content)
        except ValueError:
            raise APIError(f'No tables found for {self.symbol}, download.Holdings scraper may need to be updated')

        # Reformat dataframe
        holdings = tables[0].loc[:, ('Stock', '% ofPortfolio')]
        holdings.rename(columns={'Stock': 'symbol', '% ofPortfolio': 'pct'}, inplace=True)
        holdings['symbol'] = holdings['symbol'].apply(lambda s: s.split('-')[0].strip())
        return holdings

    def vanguard(self, progress=False):
        """Lookup ETF holdings from website"""

        # Scrape the raw HTML
        holdings = paginate_selenium_table(
            url=conf['endpoints']['vanguard'].format(self.symbol),
            progress=progress,
            **conf['css']['vanguard'])
        holdings.rename(columns={'Holdings': 'symbol'}, inplace=True)
        holdings = holdings[~holdings.symbol.isna()]

        # Some tickers won't match the regex so the lambda in ``apply`` needs a default
        # See proposed solutions here: https://stackoverflow.com/q/2492087/7446465
        symbol_regex = re.compile('\(([A-Z0-9]+)\)')
        unparseable_symbol = '<UNK>'
        holdings['symbol'] = holdings['symbol'].apply(
            lambda s: (symbol_regex.findall(s)[0:1] or [unparseable_symbol])[0])
        holdings = holdings[holdings.symbol != unparseable_symbol]

        # Percentage column comes in as rounded string, so more precise values are obtained by calculating ourselves
        holdings['Market value'] = holdings['Market value'].replace('[\$,]', '', regex=True).astype(float)
        total_value = holdings['Market value'].sum()
        holdings['pct'] = holdings['Market value'].apply(lambda m: m/total_value)
        holdings = holdings.loc[:, ('symbol', 'pct')]
        return holdings
