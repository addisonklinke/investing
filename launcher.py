import argparse
import logging
import os
import pickle
import re
import sys
import git
from stringcase import camelcase, capitalcase, snakecase
from investing import conf, download, InvestingLogging


class Launcher(InvestingLogging):
    """Define and run investing workflows.

    Each method should define a workflow (i.e. a combination of tasks using
    the other submodules in this package). The __call__ method allows the
    workflows to be easily accessed from the command line via this module's
    __main__ method.

    :param str workflow: Camel cased name of method to run.
    :param bool foreground: Whether or not to log messsages to stdout
    :param str save: Local filepath to save results to
    :param str branch: Name of git branch to use when running.
    """

    def __init__(self, workflow, foreground=False, save=None, branch='master'):
        super(Launcher, self).__init__()
        if foreground:
            stdout = logging.StreamHandler(stream=sys.stdout)
            stdout.setFormatter(self.formatter)
            self.logger.addHandler(stdout)
        self.workflow = workflow
        self.save = save
        if self.save == 'None':
            self.save = conf['paths']['save']
        self.branch = branch
        self.workflows = [capitalcase(camelcase(item)) for item in dir(self)
                          if callable(getattr(self, item)) and not item.startswith('__')]

    def __call__(self):
        """Checkout requested branch and run the desired workflow."""
        if self.workflow not in self.workflows:
            print('Expected workflow to be one of {}, but received \'{}\''.format(
                self.workflows, self.workflow))
            sys.exit(1)

        self.logger.info('Running the {} workflow on {} branch'.format(self.workflow, self.branch))
        load_stash = False
        repo = git.Repo('.')
        repo.git.config('--global', 'user.email', 'agk38@case.edu')
        repo.git.config('--global', 'user.name', 'Addison Klinke')
        branches = repo.git.branch().split('\n')
        original = re.sub('\*\s', '', branches[[i for i, b in enumerate(branches) if b.startswith('*')][0]])
        if original != self.branch:
            if repo.is_dirty():
                self.logger.info('Stashing local changes on branch {}'.format(original))
                repo.git.stash('push', '-m', 'Created by investing.workflows.Launcher')
                load_stash = True
            self.logger.info('Checking out {} branch'.format(self.branch))
            repo.git.checkout(self.branch)

        method = self.__getattribute__(snakecase(self.workflow))
        try:
            method()
        except Exception:
            self.logger.exception('Uncaught exception in {} workflow'.format(self.workflow))

        if original != self.branch:
            self.logger.info('Reverting repository to prior state')
            repo.git.checkout(original)
            if load_stash:
                repo.git.stash('pop')
        self.logger.info('Completed the {} workflow'.format(self.workflow))

    def daily_tickers(self):
        """Download new time series data for followed tickers"""
        portfolio = os.path.join(conf['paths']['save'], 'portfolios.txt')
        if not os.path.exists(portfolio):
            print(f'Portfolio list not found at {portfolio}, please run MonitorPortfolios workflow first')
            return
        with open(portfolio, 'r') as f:
            tickers = [l.strip() for l in f.read().split('\n') if l != '']
        self.logger.info('Found {} tickers to check prices for'.format(len(tickers)))
        for t in tickers:
            path = os.path.join(conf['paths']['save'], '{}.pkl'.format(t.lower()))
            if os.path.exists(path):
                current = pickle.load(open(path, 'rb'))
                ts = download.timeseries(t, 'compact')
                if len(ts) == 0:
                    self.logger.warning('No data found for {}'.format(t.upper()))
                    continue
                new = {k: v for k, v in ts.items() if k > max(current.keys())}
                current.update(new)
                pickle.dump(current, open(path, 'wb'))
                self.logger.info('{} data exists locally, appending latest'.format(t.upper()))
            else:
                ts = download.timeseries(t, 'full')
                if len(ts) == 0:
                    self.logger.warning('No data found for {}'.format(t.upper()))
                    continue
                pickle.dump(ts, open(path, 'wb'))
                self.logger.info('{} not found locally, downloading last 20 years'.format(t.upper()))

    def monitor_portfolios(self):
        """Check holdings of major investment firms such as Berkshire Hathaway"""
        held_tickers = []
        for ticker, investor in conf['following'].items():
            self.logger.info(f'Downloading holdings for {ticker}')
            held_tickers += download.holdings(ticker)
        unique = set(held_tickers)
        with open(os.path.join(conf['paths']['save'], 'portfolios.txt'), 'w') as f:
            f.write('\n'.join(unique))


if __name__ == '__main__':

    parser = argparse.ArgumentParser(
        description='Command line interface for other classes in the investing package',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('workflow', type=str, nargs='?', default='None', help='name of workflow to run')
    parser.add_argument('-b', '--branch', type=str, default='master', help='git branch to run the workflow')
    parser.add_argument('-f', '--foreground', action='store_true', help='print logs to stdout in addition to file')
    parser.add_argument('-l', '--list', action='store_true', help='display available workflows and descriptions')
    parser.add_argument('-s', '--save', type=str, default=None, help='local folder to save results in')
    args = parser.parse_args()

    if args.workflow == 'None' and not args.list:
        print('Workflow name must be supplied if --list flag is not used')
        sys.exit(1)
    launcher = Launcher(args.workflow, args.foreground, args.save, args.branch)
    if args.list:
        print('The following workflows are available')
        for w in launcher.workflows:
            doc = launcher.__getattribute__(snakecase(w)).__doc__
            print('  - {}: {}'.format(w, doc))
    else:
        launcher()
