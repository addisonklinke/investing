import base64
import hashlib
import hmac
import json
import os
import pickle
import time
from urllib.parse import quote_plus
import requests
from investing import keys


def holdings(company='berkshire'):
    url = 'https://whalewisdom.com/shell/command.json?args={}&api_shared_key={}&api_sig={}&timestamp={}'
    url_json = '{"command":"quarters"}'
    now = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    sig = _whale_wisdom_signature(url_json, now)
    api_url = url.format(quote_plus(url_json), keys['whale-wisdom']['shared'], sig, now)
    r = requests.get(api_url)
    print(r.status_code)
    print(r.content)


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


def _whale_wisdom_signature(url_json, now):
    """Create hash from secret key based on Whale Wisdom procedure.

    See https://whalewisdom.com/python3_api_sample.txt

    :param str url_json: Parameters for API endpoint.
    :param str now: Timestamp string for the request.
    :return str sig: Constructed using HMAC-SHA1 algorithm.
    """
    key = keys['whale-wisdom']['secret'].encode()
    digest = hashlib.sha1
    hash_args = '{}\n{}'.format(url_json, now).encode()
    hmac_hash = hmac.new(key, hash_args, digest).digest()
    sig = base64.b64encode(hmac_hash).rstrip().decode()
    return sig
