import json
import os
import pickle
from warnings import warn
import pandas as pd
import requests
from investing import keys, endpoints, save_dir


def holdings(ticker='BRK'):
    """Save list of stock holdings for a particular company.

    :param str ticker: Company ticker (case insensitive).
    :return [str] held_tickers: Tickers of company holdings.
    """
    r = requests.get(endpoints['dataroma'], {'m': ticker})
    tables = pd.read_html(r.content)
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
    params.update({'items': items, 'token': keys['stock-news']})
    r = requests.get(url, params)
    articles = json.loads(r.content)
    return articles


def timeseries(ticker, length='compact', out_dir=None):
    """Save JSON formatted pickle of stock prices from Alpha Vantage API.

    If ticker exists locally, new results will be appended to the current data

    :param str ticker: Uppercase stock abbreviation.
    :param str length: Either compact (last 100 days) or full (20 years).
    :param str out_dir: Directory to save pickle file
    :return: None
    """
    if out_dir is None:
        out_dir = save_dir
    r = requests.get(
        url=endpoints['alpha-vantage'],
        params={
            'function': 'TIME_SERIES_DAILY',
            'symbol': ticker.upper(),
            'outputsize': length,
            'apikey': keys['alpha-vantage']})
    data = json.loads(r.content)
    try:
        ts = {k: float(v['4. close']) for k, v in data['Time Series (Daily)'].items()}
    except KeyError:
        raise ValueError('Invalid stock ticker {}'.format(ticker))
    fpath = os.path.join(out_dir, '{}.pkl'.format(ticker.lower()))
    if os.path.exists(fpath):
        current = pickle.load(open(fpath, 'rb'))
        new = {k: v for k, v in ts.items() if k > max(current.keys())}
        current.update(new)
        pickle.dump(current, open(fpath, 'wb'))
    else:
        pickle.dump(ts, open(fpath, 'wb'))
