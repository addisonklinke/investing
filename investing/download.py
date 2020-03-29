import json
import os
import pandas as pd
import requests
from warnings import warn
from . import conf, endpoints
from .utils import is_current


def holdings(ticker):
    """Save list of stock holdings for a particular company.

    :param str ticker: Company ticker (case insensitive).
    :return [str] held_tickers: Tickers of company holdings.
    """
    r = requests.get(endpoints['dataroma'], {'m': ticker}, headers={"User-Agent": "XY"})
    try:
        tables = pd.read_html(r.content)
    except ValueError:
        raise RuntimeError(f'No tables found for {ticker}, download.holdings() scraper may need to be updated')
    holdings = tables[0]
    held_tickers = [s.split('-')[0].strip() for s in holdings.Stock]
    return held_tickers


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
    url = endpoints['finnhub']['news']
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
    url = endpoints['finnhub']['sentiment']
    params = {
        'symbol': ticker,
        'token': conf['keys']['finnhub']}
    r = requests.get(url, params)
    data = json.loads(r.content)
    if not r.ok:
        raise RuntimeError(f'Bad status code {r.status_code} from Finnhub sentiment')
    return data['companyNewsScore']


def ticker_data(ticker):
    """Helper function to refresh local ticker data or fetch if missing

    :param str ticker: Stock ticker symbol (case-insensitive)
    :return str status: One of the following
        * current: No API call needed, local data is up-to-date
        * missing: No remote data found, perhaps an incorrect ticker symbol
        * full: No previous local data was found, downloaded full from API
        * compact: Previous local data was refreshed with more recent API data
    """
    path = os.path.join(conf['paths']['save'], '{}.csv'.format(ticker.lower()))
    if os.path.exists(path):
        if is_current(ticker):
            return 'current'
        length = 'compact'
        existing = pd.read_csv(path)
    else:
        length = 'full'
        existing = None
    ts = timeseries(ticker, length)
    if len(ts) == 0:
        return 'missing'
    new = pd.DataFrame.from_dict(ts, orient='index', columns=['price'])
    new['date'] = new.index
    if existing is not None:
        combined = pd.concat([new, existing])
        combined = combined[~combined.date.duplicated()]
    else:
        combined = new
    combined.to_csv(path, index=False)
    return length


def timeseries(ticker, length='compact'):
    """Download stock prices from Alpha Vantage API.

    :param str ticker: Uppercase stock abbreviation.
    :param str length: Either compact (last 100 days) or full (20 years).
    :return dict ts: Timestamps as keys and closing prices as values.
    """
    r = requests.get(
        url=endpoints['alpha-vantage'],
        params={
            'function': 'TIME_SERIES_DAILY',
            'symbol': ticker.upper(),
            'outputsize': length,
            'apikey': conf['keys']['alpha-vantage']})
    if not r.ok:
        raise RuntimeError(f'AlphaVantage API bad status code {r.status_code}')
    try:
        data = json.loads(r.content)
        ts = {k: float(v['4. close']) for k, v in data['Time Series (Daily)'].items()}
    except KeyError:
        warn(f'Error retrieving ticker {ticker}')
        ts = {}
    return ts
