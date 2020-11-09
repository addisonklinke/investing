from datetime import date, datetime, timedelta
import numpy as np
import pandas as pd


def get_dummy_data(num_days, low, high, end_date='1970-01-01'):
    """Generate linearly increasing price data for unit tests

    :param int num_days: Length of timeseries
    :param int low: Starting price
    :param int high: Ending price (inclusive)
    :param str end_date: YYYY-MM-DD timestamp for end of data (inclusive)
    :return pd.DataFrame df:
    """
    step = (high - low) / (num_days - 1)
    ref = datetime.strptime(end_date, '%Y-%m-%d').date()
    start_dt = ref - timedelta(days=(num_days - 1))
    end_dt = ref + timedelta(days=1)
    ts = np.arange(start_dt, end_dt, timedelta(days=1)).astype(date)
    df = pd.DataFrame(data={'price': np.arange(low, high + 1, step)}, index=pd.DatetimeIndex(ts))
    return df
