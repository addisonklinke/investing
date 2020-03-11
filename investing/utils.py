import argparse
from datetime import date, datetime, timedelta
import pandas_market_calendars as mcal
import pytz
from . import conf
from .data import Ticker


def is_current(ticker):
    """Check if ticker CSV has the most recent data

    :param str ticker: Ticker symbol to check
    :return bool: Whether the latest timestamp matches the last market day
    """
    latest_close = market_day('current')
    t = Ticker(ticker)
    return latest_close <= t.data.date.max()


def market_day(direction):
    """Return the closest completed and valid market day

    :param str direction: One of previous, current, next
    :return np.datetime64: Date stamp
    """
    nyse = mcal.get_calendar('NYSE')
    recent = nyse.valid_days(start_date=date.today() - timedelta(days=7), end_date=date.today() + timedelta(days=1))
    idx = -2  # Last series index is the 1 day in the future
    current_close = nyse.schedule(start_date=recent[idx], end_date=recent[idx]).market_close[0]
    tz = pytz.timezone(conf['locale'])
    if current_close > datetime.now(tz):
        idx -= 1
    if direction == 'current':
        stamp = recent[idx]
    elif direction == 'previous':
        stamp = recent[idx - 1]
    elif direction == 'next':
        stamp = recent[idx + 1]
    else:
        raise ValueError(f'Expected direction to be previous, current, or next, but received {direction}')
    return stamp.to_numpy()


def ptable_to_csv(table, filename, headers=True):
    """Save PrettyTable results to a CSV file.

    Adapted from @AdamSmith https://stackoverflow.com/questions/32128226

    :param PrettyTable table: Table object to get data from.
    :param str filename: Filepath for the output CSV.
    :param bool headers: Whether to include the header row in the CSV.
    :return: None
    """
    raw = table.get_string()
    data = [tuple(filter(None, map(str.strip, splitline)))
            for line in raw.splitlines()
            for splitline in [str(line).split('|')] if len(splitline) > 1]
    if hasattr(table, 'title') and table.title is not None:
        data = data[1:]
    if not headers:
        data = data[1:]
    with open(filename, 'w') as f:
        for d in data:
            f.write('{}\n'.format(','.join(d)))


class SubCommandDefaults(argparse.ArgumentDefaultsHelpFormatter):
    """Corrected _max_action_length for the indenting of subactions

    This is a known bug (https://bugs.python.org/issue25297) in Python's argparse
    with a patch solution provided from https://stackoverflow.com/a/32891625/7446465
    """
    def add_argument(self, action):
        if action.help is not argparse.SUPPRESS:

            # Find all invocations
            get_invocation = self._format_action_invocation
            invocations = [get_invocation(action)]
            current_indent = self._current_indent
            for subaction in self._iter_indented_subactions(action):
                # compensate for the indent that will be added
                indent_chg = self._current_indent - current_indent
                added_indent = 'x'*indent_chg
                invocations.append(added_indent+get_invocation(subaction))

            # Update the maximum item length
            invocation_length = max([len(s) for s in invocations])
            action_length = invocation_length + self._current_indent
            self._action_max_length = max(self._action_max_length, action_length)

            # Add the item to the list
            self._add_item(self._format_action, [action])
