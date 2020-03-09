import argparse
import logging
import os
import sys
from time import sleep
import pandas as pd
from prettytable import PrettyTable
import yaml
from investing import conf, download, InvestingLogging
from investing.data import Ticker


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


class Launcher(InvestingLogging):
    """Define and run investing workflows.

    Each method should define a workflow (i.e. a combination of tasks using
    the other submodules in this package). The main parser allows the
    workflows to be easily accessed from the command line. Workflow specific
    arguments can be added via the ``subparsers`` dict

    :param str workflow: Camel cased name of method to run.
    :param bool foreground: Whether or not to log messsages to stdout
    :param str save: Local filepath to save results to
    :param str branch: Name of git branch to use when running.
    """

    # TODO commands to add
    #     Search/list existing local tickers
    #     Init config values (i.e. write API keys to YAML)

    def __init__(self):
        super(Launcher, self).__init__()

        # Add subparsers to top-level parser for each workflow method
        workflows = [item for item in dir(self) if callable(getattr(self, item)) and not item.startswith('_')]
        parser = argparse.ArgumentParser(
            formatter_class=lambda prog: SubCommandDefaults(prog, width=120, max_help_position=50))
        parser.add_argument('-f', '--foreground', action='store_true', help='print logs to stdout in addition to file')
        manager = parser.add_subparsers(dest='workflow', metavar='workflow')
        subparsers = {}
        for w in workflows:
            doc = getattr(self, w).__doc__
            subparsers.update({w: manager.add_parser(w, description=doc, help=doc)})

        # Add workflow-specific args to each subparser
        comp_perf = subparsers['compare_performance']
        comp_perf.add_argument('format', choices=['pdf', 'console'], help='output report format')
        comp_perf.add_argument('tickers', type=str, help='comma separated ticker symbols')
        comp_perf.add_argument('-l', '--local_only', action='store_true', help='don\'t download more recent data')
        args = parser.parse_args()
        if args.workflow is None:
            print('workflow is required')
            sys.exit(1)

        # Setup logging
        if args.foreground:
            stdout = logging.StreamHandler(stream=sys.stdout)
            stdout.setFormatter(self.formatter)
            self.logger.addHandler(stdout)

        # Run workflow
        self.logger.info(f'Running the {args.workflow} workflow')
        try:
            getattr(self, args.workflow)(args)
        except Exception:
            self.logger.exception(f'Uncaught exception in {args.workflow} workflow')
        self.logger.info(f'Completed the {args.workflow} workflow')

    def _get_portfolio(self):
        """Helper function to load tickers defined in user's portfolio"""
        portfolio = os.path.join(conf['paths']['save'], 'portfolios.txt')
        if not os.path.exists(portfolio):
            print(f'Portfolio list not found at {portfolio}, please run monitor_portfolios workflow first')
            return []
        with open(portfolio, 'r') as f:
            tickers = [l.strip() for l in f.read().split('\n') if l != '']
        return tickers

    def _refresh_tickers(self, tickers):
        """Helper function to get most recent ticker data

        :param [str] tickers: Stock ticker symbols (case-insensitive)
        :return: None
        """
        self.logger.info('Sleeping for 12 seconds between API calls (AlphaVantage free tier limitation)')
        for i, t in enumerate(tickers):
            path = os.path.join(conf['paths']['save'], '{}.csv'.format(t.lower()))
            if os.path.exists(path):
                length = 'compact'
                existing = pd.read_csv(path)
                # TODO check the latest timestamp and skip API call if up-to-date
            else:
                length = 'full'
                existing = None
            ts = download.timeseries(t, length)
            if len(ts) > 0:
                self.logger.info(f'Downloaded {i + 1}/{len(tickers)}: {t.upper()} ({length})')
            else:
                self.logger.warning(f'No data found for {t.upper()}')
                continue
            new = pd.DataFrame.from_dict(ts, orient='index', columns=['price'])
            new['date'] = new.index
            if existing is not None:
                combined = pd.concat([new, existing])
                combined = combined[~combined.date.duplicated()]
            else:
                combined = new
            combined.to_csv(path, index=False)
            sleep(12)

    def compare_performance(self, args):
        """Generate plain text or PDF formatted report of stock performance"""

        def format_percent(p, decimals=2):
            return f'{p * 100:.{decimals}f}%'

        tickers = [t.strip() for t in args.tickers.split(',')]
        self.logger.info(f'Received {len(tickers)} symbols to compare performance of')
        if args.local_only:
            self.logger.info('Using most recent local data')
        else:
            self.logger.info('Refreshing local data from Alpha Vantage')
            self._refresh_tickers(tickers)
        comparison = PrettyTable()
        comparison.field_names = [
            'Ticker', 'Name', '1-Year Rolling', '3-Year Rolling', '5-Year Rolling', '10-Year Rolling']
        for t in tickers:
            ticker = Ticker(t)
            comparison.add_row([
                t.upper(),
                ticker.name,
                format_percent(ticker.rolling('1-year')),
                format_percent(ticker.rolling('3-year')),
                format_percent(ticker.rolling('5-year')),
                format_percent(ticker.rolling('10-year'))])
        print(comparison)

    def daily_tickers(self, args):
        """Download new time series data for followed tickers"""
        tickers = self._get_portfolio()
        if len(tickers) == 0:
            return
        self.logger.info(f'Found {len(tickers)} tickers to check prices for')
        self._refresh_tickers(tickers)

    def monitor_portfolios(self, args):
        """Check holdings of major investment firms such as Berkshire Hathaway"""
        held_tickers = []
        for ticker, investor in conf['following'].items():
            self.logger.info(f'Downloading holdings for {ticker}')
            held_tickers += download.holdings(ticker)
        unique = set(held_tickers)
        with open(os.path.join(conf['paths']['save'], 'portfolios.txt'), 'w') as f:
            f.write('\n'.join(unique))

    def show_config(self, args):
        """Print active configuration values to console for confirmation"""
        stream = yaml.dump(conf)
        print(stream.replace('\n-', '\n -'))


if __name__ == '__main__':

    Launcher()
