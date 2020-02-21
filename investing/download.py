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


def news(ticker=None, items=50):
    """Gather news articles for general market or a specific ticker.

    :param str ticker: Defaults to ``None`` for general market news.
    :param int items: Number of articles to return (max allowed for free
        subscription is 50).
    :return dict articles: JSON formatted news articles.
    """
    if items > 50:
        warn('More than 50 items is not supported by free tier')
    url = endpoints['stock-news']
    if ticker is not None:
        params = {'tickers': ticker}
    else:
        url = os.path.join(url, 'cateogry')
        params = {'section': 'alltickers'}
    params.update({'items': items, 'token': conf['keys']['stock-news']})
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
