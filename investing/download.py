import json
import os
import pandas as pd
import requests
from warnings import warn
from . import conf, endpoints


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
