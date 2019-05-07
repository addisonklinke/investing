import base64
import hashlib
import hmac
import json
import os
import pickle
import time
from warnings import warn
import requests
from investing import keys, endpoints


def filer_id(company):
    """Get Whale Wisdom internal ID for filer.

    :param str company: Name of the company (does not have to be exact).
    :return int id: None if no matches were found.
    """
    url_json = '{{"command":"filer_lookup", "name":"{}"}}'.format(company)
    sig, now = _whale_wisdom_signature(url_json)
    r = requests.get(
        url=endpoints['whale-wisdom'],
        params={
            'args': url_json,
            'api_shared_key': keys['whale-wisdom']['shared'],
            'api_sig': sig,
            'timestamp': now})
    data = json.loads(r.content)
    if len(data['filers']) > 1:
        warn('Multiple matches for {}, defaulting to first'.format(company))
    if len(data['filers']) > 0:
        id = data['filers'][0]['id']
    else:
        id = None
    return id


def holdings(company='BERKSHIRE HATHAWAY INC'):
    """Save list of stock holdings for a particular company.

    :param str company: Name of the company (does not have to be exact).
    :return: None
    """
    id = filer_id(company)
    url_json = '{{"command":"holdings", "filer_ids":[{}]}}'.format(id)
    sig, now = _whale_wisdom_signature(url_json)
    r = requests.get(
        url=endpoints['whale-wisdom'],
        params={
            'args': url_json,
            'api_shared_key': keys['whale-wisdom']['shared'],
            'api_sig': sig,
            'timestamp': now})
    print(r.status_code)
    print(r.content)


def stock_news(ticker=None, items=50):
    params = {'token': keys['stock-news'], 'items': items}
    if ticker is not None:
        params.update({'tickers': ticker})
    else:
        params.update({'section': 'alltickers'})
    r = requests.get(endpoints['stock-news'], params)


def timeseries(symbol, length='compact', out_dir='/mnt/stocks'):
    """Save JSON formatted pickle of stock prices from Alpha Vantage API.

    If symbol exists locally, new results will be appended to the current data

    :param str symbol: Uppercase stock abbreviation.
    :param str length: Either compact (last 100 days) or full (20 years).
    :param str out_dir: Directory to save pickle file
    :return: None
    """
    url = 'https://www.alphavantage.co/query?function=TIME_SERIES_DAILY&symbol={}&outputsize={}&apikey={}'
    r = requests.get(url.format(symbol, length, keys['alpha-vantage']))
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


def _whale_wisdom_signature(url_json):
    """Create hash from secret key based on Whale Wisdom procedure.

    See https://whalewisdom.com/python3_api_sample.txt

    :param str url_json: Parameters for API endpoint.
    :param str now: Timestamp string for the request.
    :return tuple: Signature from HMAC-SHA1 algorithm and timestamp.
    """
    key = keys['whale-wisdom']['secret'].encode()
    digest = hashlib.sha1
    now = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    hash_args = '{}\n{}'.format(url_json, now).encode()
    hmac_hash = hmac.new(key, hash_args, digest).digest()
    sig = base64.b64encode(hmac_hash).rstrip().decode()
    return sig, now
