"""Retrieve data from configured API endpoints"""

import json
import os
import pandas as pd
import requests
from . import conf, endpoints
from .exceptions import APIError


def holdings(ticker):
    """Save list of stock holdings for a particular company.

    :param str ticker: Company ticker (case insensitive).
    :return [str] held_tickers: Tickers of company holdings.
    """
    r = requests.get(endpoints['dataroma'], {'m': ticker}, headers={"User-Agent": "XY"})
    try:
        tables = pd.read_html(r.content)
    except ValueError:
        raise APIError(f'No tables found for {ticker}, download.holdings() scraper may need to be updated')
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
        url=endpoints['alpha-vantage'],
        params={
            'function': 'TIME_SERIES_DAILY',
            'symbol': ticker.upper(),
            'outputsize': length,
            'apikey': conf['keys']['alpha-vantage']})
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
