import argparse
import logging
import math
import os
import sys
from time import sleep
import pandas as pd
from prettytable import PrettyTable
import yaml
from investing import conf, download, InvestingLogging
from investing.data import Portfolio, Ticker
from investing.download import ticker_data
from investing.mappings import ticker2name
from investing.utils import is_current, ptable_to_csv, SubCommandDefaults


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
    #     Init config values (i.e. write API keys to YAML)
    # TODO alternate constructor for non-CLI use
    # TODO longer method docstrings for Sphinx, but only first line in argparse

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
        comp_perf.add_argument('tickers', type=str, help='comma separated ticker symbols')
        comp_perf.add_argument('format', nargs='?', choices=['pdf', 'csv'], help='optional output report format')
        comp_perf.add_argument('-l', '--local_only', action='store_true', help='don\'t download more recent data')
        expected_return = subparsers['expected_return']
        expected_return.add_argument('tickers', type=str, help='comma separated ticker symbols')
        expected_return.add_argument('holding_periods', type=str, help='comma separated financial period keyword(s)')
        expected_return.add_argument('weights', nargs='?', help='proportion of each ticker (assumed equal if absent)')
        expected_return.add_argument('-l', '--local_only', action='store_true', help='don\'t download more recent data')
        expected_return.add_argument('-n', '--num_trials', type=int, default=1000, help='number of Monte Carlo trials')
        subparsers['search'].add_argument('ticker', type=str, help='symbol to search for (case insensitive)')
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
            self.logger.info(f'Completed the {args.workflow} workflow')
        except Exception:
            msg = f'Uncaught exception in {args.workflow} workflow'
            if not args.foreground:
                print(f'{msg}, rerun with -f to see details')
            self.logger.exception(msg)

    def _format_percent(self, p, decimals=2):
        """Convert decimal percentage to human-readable string

        :param float p: Raw percentage
        :param int decimals: Precision of displayed value
        :return str: Human-readable representation
        """
        if math.isnan(p):
            return 'NaN'
        else:
            return f'{p * 100:.{decimals}f}%'

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
            try:
                status = ticker_data(t)
            except RuntimeError:
                self.logger.exception(f'Timeseries download error, skipping {t.upper()}')
                continue
            if status == 'current':
                self.logger.info(f'{i + 1}/{len(tickers)}: {t.upper()} already up-to-date')
                continue
            elif status in ['compact', 'full']:
                self.logger.info(f'{i + 1}/{len(tickers)}: downloaded {t.upper()} ({status})')
            elif status == 'missing':
                self.logger.warning(f'No data found for {t.upper()}')
                continue
            else:
                raise ValueError(f'Unknown status string {status} from download.ticker_data()')
            sleep(12)

    def compare_performance(self, args):
        """Calculate historical performance for several stock(s)"""

        # Setup data sources
        tickers = [t.strip() for t in args.tickers.split(',')]
        self.logger.info(f'Received {len(tickers)} symbols to compare performance of')
        if args.local_only:
            self.logger.info('Using most recent local data')
        else:
            self.logger.info('Refreshing local data from Alpha Vantage')
            self._refresh_tickers(tickers)

        # Calculate statistics
        comparison = PrettyTable()
        comparison.field_names = ['Ticker', 'Name'] + [m.title() for m in conf['metrics']]
        for t in tickers:
            ticker = Ticker(t)
            comparison.add_row(
                [t.upper(), ticker.name] + [self._format_percent(ticker.metric(m)) for m in conf['metrics']])

        # Output to requested format
        print(comparison)
        if args.format == 'csv':
            self.logger.info('Saving results to comparison.csv')
            ptable_to_csv(comparison, 'comparison.csv')
        elif args.format == 'pdf':
            raise NotImplementedError('PDF report format is not yet supported')

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

    def expected_return(self, args):
        """Calculate joint return probability across several holdings"""

        # Initialize portfolio object
        tickers = [t for t in args.tickers.split(',')]
        if args.weights is None:
            weights = None
        else:
            weights = [float(w) for w in args.weights.split(',')]
        portfolio = Portfolio(tickers, weights)
        self.logger.info(f'Initialized portfolio object {portfolio}')

        # Calculate returns and print results
        returns = PrettyTable()
        returns.field_names = ['Period', '-σ', 'Mean', '+σ', 'Data Points']
        returns.title = portfolio.name
        periods = [p for p in args.holding_periods.split(',')]
        self.logger.info(f'Simulating composite returns for {periods}')
        for p in periods:
            return_avg, return_std, min_count = portfolio.expected_return(p, args.num_trials)
            returns.add_row([
                p,
                self._format_percent(return_avg - return_std),
                self._format_percent(return_avg),
                self._format_percent(return_avg + return_std),
                min_count])
        print(returns)

    def search(self, args):
        """Check if ticker data exists locally"""
        tick_up = args.ticker.upper()
        tick_low = args.ticker.lower()
        csv_path = os.path.join(conf['paths']['save'], f'{tick_low}.csv')
        name = ticker2name.get(tick_up, 'Unknown')
        if os.path.exists(csv_path):
            status = 'Found'
            if not is_current(tick_low):
                status += ' stale'
        else:
            status = 'Missing'
        msg = f'{status} local data for {tick_up}'
        if name == 'Unknown':
            msg += ' - name not in mappings.ticker2name, please submit pull request'
        else:
            msg += f' ({name})'
        print(msg)
        return status == 'found'

    def show_config(self, args):
        """Print active configuration values to console for confirmation"""
        stream = yaml.dump(conf)
        print(stream.replace('\n-', '\n  -'))


if __name__ == '__main__':

    Launcher()
