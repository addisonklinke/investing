import argparse
from glob import glob
from itertools import chain
import logging
import math
import os
import re
import sys
from time import sleep
from prettytable import PrettyTable
import pytz
import yaml
from investing import __version__
from investing import conf, InvestingLogging
from investing.data import Portfolio, Ticker
from investing.download import Holdings
import investing.exceptions as exceptions
import investing.mappings as mappings
from investing.utils import partition, ptable_to_csv, sort_with_na, SubCommandDefaults

# TODO explicit submodule imports with "import investing.x as x"
# TODO workflow to list configured tickers without name in mapping


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

    def __init__(self):
        super(Launcher, self).__init__()

        # Add subparsers to top-level parser for each workflow method
        workflows = [item for item in dir(self) if callable(getattr(self, item)) and not item.startswith('_')]
        parser = argparse.ArgumentParser(
            formatter_class=lambda prog: SubCommandDefaults(prog, width=120, max_help_position=50))
        parser.add_argument('-f', '--foreground', action='store_true', help='print logs to stdout in addition to file')
        parser.add_argument('-v', '--version', action='store_true', help='print package version')
        manager = parser.add_subparsers(dest='workflow', metavar='workflow')
        subparsers = {}
        for w in workflows:
            doc = getattr(self, w).__doc__
            subparsers.update({w: manager.add_parser(w, description=doc, help=doc)})

        # Add workflow-specific args to each subparser
        cols = ['ticker', 'name', 'metric']
        comp_perf = subparsers['compare_performance']
        comp_perf.add_argument('tickers', type=str, help='comma separated ticker symbols (or portfolio names)')
        comp_perf.add_argument('-l', '--local_only', action='store_true', help='don\'t download more recent data')
        comp_perf.add_argument('-m', '--metrics', type=str, help='comma separate metric keywords')
        comp_perf.add_argument('-p', '--portfolios', action='store_true', help='add column with portfolio name')
        comp_perf.add_argument('-s', '--sort', type=str, choices=cols, default='metric', help='sorting column')

        subparsers['download'].add_argument('symbols', type=str, help='tickers (case insensitive) or portfolio names')

        expected_return = subparsers['expected_return']
        expected_return.add_argument('tickers', type=str, help='comma separated ticker symbols')
        expected_return.add_argument('holding_periods', type=str, help='comma separated financial period keyword(s)')
        expected_return.add_argument('weights', nargs='?', help='proportion of each ticker (assumed equal if absent)')
        expected_return.add_argument('-l', '--local_only', action='store_true', help='don\'t download more recent data')
        expected_return.add_argument('-n', '--num_trials', type=int, default=1000, help='number of Monte Carlo trials')

        subparsers['search'].add_argument('ticker', type=str, help='symbol to search for (case insensitive)')

        show_config = subparsers['show_config']
        show_config.add_argument('-p', '--portfolios', action='store_true', help='only show portfolio names')
        args = parser.parse_args()

        # Validate configuration
        if not os.path.isdir(conf['paths']['save']):
            raise exceptions.ImproperlyConfigured(f'Save directory {conf["paths"]["save"]} does not exist')
        for api, key in conf['keys'].items():
            if key is None:
                raise exceptions.ImproperlyConfigured(f'No API key configured for {api}')
        valid_name = re.compile('^[a-z0-9_]+$')
        for name, info in conf['portfolios'].items():
            if not valid_name.match(name):
                raise exceptions.ImproperlyConfigured(
                    f"Name can only contain lowercase letters, numbers, and underscores: '{name}'")
            if name in mappings.ticker2name:
                raise exceptions.ImproperlyConfigured(f"Portfolio name cannot match ticker symbol: '{name}'")
            portfolio_type = info.get('type')
            if portfolio_type not in ['follow', 'manual']:
                raise exceptions.ImproperlyConfigured(f'Unknown type {portfolio_type} for {p["name"]} portfolio')
            if len(info.get('symbols', [])) == 0:
                raise exceptions.ImproperlyConfigured(f'Portfolio {info["name"]} has no symbols defined')

        # Shared attributes
        self.ticker2portfolio = {t: name for name, info in conf['portfolios'].items() for t in info['symbols']}

        # Check parsed arguments
        if args.version:
            print(__version__)
            sys.exit(0)
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
            return f'{p * 100:.{decimals}f}'

    def _load_portfolios(self, portfolios=None):
        """Helper function to load unique tickers defined in user's portfolios

        Sort returned tickers for better reproducibility in calling scopes
        like ``_refresh_tickers``. If a followed portfolio has the ``shared``
        flag enabled, only include commonly held tickers

        :param Union[Dict, List[str]] portfolios: Specific portfolio object or name(s)
            to load, otherwise all
        :return [str] tickers: Ticker symbols belonging to the portfolio(s)
        """
        tickers = []

        # Determine requested format
        if isinstance(portfolios, str):
            portfolios = [portfolios]
        if portfolios is None:
            portfolios = conf['portfolios']
        elif isinstance(portfolios, list):
            portfolios = {k: v for k, v in conf['portfolios'].items() if k in portfolios}

        # Build the tickers list
        for name, info in portfolios.items():
            if info['type'] == 'manual':
                tickers += info['symbols']
            elif info['type'] == 'follow':
                held = {}
                for s in info['symbols']:
                    self.logger.info(f'Downloading holdings for {s}')
                    held[s] = Holdings(s).download()
                if info.get('shared', False):
                    shared = list(set.intersection(*[set(s) for s in held.values()]))
                    if len(shared) == 0:
                        self.logger.warning(f'No shared tickers in {name} portfolio: {", ".join(info["symbols"])}')
                    tickers += shared
                else:
                    tickers += list(chain(*held.values()))
        return sorted(list(set(tickers)))

    def _refresh_tickers(self, tickers):
        """Helper function to get most recent ticker data

        :param [str] tickers: Stock ticker symbols (case-insensitive)
        :return: None
        """
        self.logger.info('Sleeping for 12 seconds between API calls (AlphaVantage free tier limitation)')
        for i, t in enumerate(tickers, 1):
            ticker = Ticker(t)
            if ticker.is_current:
                self.logger.info(f'{i}/{len(tickers)}: {ticker.symbol} already up-to-date')
                continue
            try:
                ticker.refresh()
            except exceptions.APIError:
                self.logger.exception(f'Timeseries download error, skipping {ticker.symbol}')
                continue
            self.logger.info(f'{i}/{len(tickers)}: refreshed {ticker.symbol}')
            sleep(12)

    def clean_csvs(self, args):
        """Delete local CSVs that are not used in portfolios"""
        tickers = self._load_portfolios()
        csvs = glob(os.path.join(conf['paths']['save'], '*.csv'))
        removed = 0
        for c in csvs:
            name = os.path.basename(c).split('.')[0]
            if name.upper() not in tickers:
                os.remove(c)
                removed += 1
        self.logger.info(f'Removed {removed} of {len(csvs)} CSVs')

    def compare_performance(self, args):
        """Calculate historical performance for several stock(s)"""

        # Setup data sources
        requested = [t.strip() for t in args.tickers.split(',')]
        portfolio_names, tickers = partition(requested, lambda t: t in list(conf['portfolios'].keys()))
        for p in portfolio_names:
            portfolio = {p: conf['portfolios'][p]}
            tickers.extend(self._load_portfolios(portfolio))
        self.logger.info(f'Received {len(tickers)} symbols to compare performance of')
        if args.local_only:
            self.logger.info('Using most recent local data')
        else:
            self.logger.info('Refreshing local data from Alpha Vantage')
            self._refresh_tickers(tickers)

        # Calculate statistics
        comparison = PrettyTable()
        if args.metrics is None:
            metrics = conf['metrics']
        else:
            metrics = [m.strip() for m in args.metrics.split(',')]
        meta_columns = ['Ticker', 'Name']
        if args.portfolios:
            meta_columns.insert(1, 'Portfolio')
        comparison.field_names = meta_columns + [m for m in metrics]
        rows = []
        for t in tickers:
            ticker = Ticker(t)
            metadata = [t.upper(), ticker.name]
            if args.portfolios:
                metadata.insert(1, self.ticker2portfolio[t])
            performance = [self._format_percent(ticker.metric(m)) for m in metrics]
            rows.append(metadata + performance)

        # Output to console and CSV
        if args.sort == 'metric':
            rows = sorted(rows, key=lambda r: sort_with_na(float(r[-1]), reverse=True))
        elif args.sort == 'ticker':
            rows = sorted(rows, key=lambda r: r[0])
        elif args.sort == 'name':
            rows = sorted(rows, key=lambda r: r[1].lower())
        else:
            self.logger.warning(f"Unknown sorting '{args.sort}', argparse should have raised error")
        for r in rows:
            comparison.add_row(r)
        print(comparison)
        self.logger.info('Saving results to comparison.csv')
        ptable_to_csv(comparison, 'comparison.csv')

    def configure(self, args):
        """Populate YAML fields on initial install"""
        print('Please enter the following values to configure your investing install')
        save_path = input('Directory to save local stock CSV data: ')
        while not os.path.isdir(save_path):
            save_path = input('Please enter a valid directory path: ')
        locale = input('Your timezone (i.e. US/Mountain, US/Eastern, etc): ')
        while locale not in pytz.all_timezones:
            locale = input('Please enter a valid timezone or all to show list: ')
            if locale == 'all':
                print('\n'.join(pytz.all_timezones))
        finnhub_key = input('Finnhub API key (see https://finnhub.io/register): ')
        alpha_vantage_key = input('AlphaVantage API key (see https://www.alphavantage.co/support/#api-key): ')
        metals_key = input('Metals API key (see https://metals-api.com/pricing): ')
        config_data = {
            'locale': locale,
            'keys': {
                'alpha_vantage': alpha_vantage_key,
                'finnhub': finnhub_key,
                'metals': metals_key},
            'paths': {
                'save': save_path}}
        with open('config/investing.yaml', 'w') as stream:
            yaml.dump(config_data, stream)
        print('Configuration successfully written')
        print("Please run 'python launcher.py show_config' to confirm")

    def download(self, args):
        """Download ticker data for specific symbols or portfolios"""

        # Default action is to download all configured tickers from all portfolios
        if args.symbols is None:
            tickers = self._load_portfolios()
            suffix = 'configured tickers'

        # Otherwise the specified arg may be either portfolio names or tickers
        else:
            symbols = args.symbols.split(',')
            tickers = self._load_portfolios([portfolio.strip() for portfolio in symbols])
            if len(tickers) > 0:
                suffix = f"tickers from portfolio(s) '{args.symbols}'"
            else:
                tickers = [ticker.strip() for ticker in symbols]
                suffix = f"requested ticker(s): '{args.symbols}'"

        # All options refresh tickers through the same method
        self.logger.info(f'Checking prices for {len(tickers)} {suffix}')
        self._refresh_tickers(tickers)

    def expected_return(self, args):
        """Calculate joint return probability across several holdings"""

        # Initialize portfolio object
        tickers = [t for t in args.tickers.split(',')]
        if args.weights is None:
            weights = None
        else:
            weights = [float(w) for w in args.weights.split(',')]
        portfolio = Portfolio(tickers, weights)
        self.logger.info(f'Initialized {repr(portfolio)}')

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
        self.logger.info('Saving results to returns.csv')
        ptable_to_csv(returns, 'returns.csv')

    def list(self, args):
        """Print all locally available ticker symbols alphabetically sorted"""
        local = [os.path.splitext(f)[0] for f in os.listdir(conf['paths']['save']) if f.endswith('.csv')]
        print('\n'.join(sorted(local)))

    def search(self, args):
        """Check if ticker data exists locally"""
        ticker = Ticker(args.ticker)
        if ticker.has_csv:
            status = 'Found'
            if not ticker.is_current:
                status += ' stale'
        else:
            status = 'Missing'
        msg = f'{status} local data for {ticker.symbol}'
        if ticker.name == 'Unknown':
            msg += ' - name not in mappings.ticker2name, please submit pull request'
        else:
            msg += f' ({ticker.name})'
        print(msg)

    def show_config(self, args):
        """Print active configuration values to console for confirmation"""
        if args.portfolios:
            for name, info in conf['portfolios'].items():
                print(f'{name} ({len(info["symbols"])} tickers)')
        else:
            stream = yaml.dump(conf)
            print(stream.replace('\n-', '\n  -'))


if __name__ == '__main__':

    Launcher()
