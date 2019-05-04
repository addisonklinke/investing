import json
import os
import pickle
import requests
from investing import key


def timeseries(symbol, length='compact', out_dir='/mnt/stocks'):
    """Save JSON formatted pickle of stock prices from Alpha Vantage API.

    If symbol exists locally, new results will be appended to the current data

    :param str symbol: Uppercase stock abbreviation.
    :param str length: Either compact (last 100 days) or full (20 years).
    :param str out_dir: Directory to save pickle file
    :return: None
    """
    url = 'https://www.alphavantage.co/query?function=TIME_SERIES_DAILY&symbol={}&outputsize={}&apikey={}'
    r = requests.get(url.format(symbol, length, key))
    data = json.loads(r.content)
    try:
        ts = {k: float(v['4. close']) for k, v in data['Time Series (Daily)'].items()}
    except KeyError:
        raise ValueError('Invalid stock symbol {}'.format(symbol))
    fpath = os.path.join(out_dir, '{}.pkl'.format(symbol.lower()))
    if os.path.exists(fpath):
        current = pickle.load(open(fpath, 'rb'))
        new = {k: v for k, v in ts.items() if k > max(current.keys())}
        current.update(new)
        pickle.dump(current, open(fpath, 'wb'))
    else:
        pickle.dump(ts, open(fpath, 'wb'))
