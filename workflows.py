import argparse
import os
import re
import sys
import git
from stringcase import camelcase, capitalcase, snakecase
import investing
import investing.download as download


class Launcher(investing.InvestingLogging):
    """Define and run investing workflows.

    Each method should define a workflow (i.e. a combination of tasks using
    the other submodules in this package). The __call__ method allows the
    workflows to be easily accessed from the command line via this module's
    __main__ method.

    :param str workflow: Camel cased name of method to run.
    :param str save: Local filepath to save results to
    :param str branch: Name of git branch to use when running.
    """

    def __init__(self, workflow, save=None, branch='master'):
        super(Launcher, self).__init__()
        self.workflow = workflow
        self.save = save
        if self.save == 'None':
            self.save = investing.conf['paths']['save']
        self.branch = branch
        self.workflows = [capitalcase(camelcase(item)) for item in dir(self)
                          if callable(getattr(self, item)) and not item.startswith('__')]

    def __call__(self):
        """Checkout requested branch and run the desired workflow."""
        if self.workflow not in self.workflows:
            print('Expected workflow to be one of {}, but received \'{}\''.format(
                self.workflows, self.workflow))
            sys.exit(1)

        self.logger.info('Running the {} workflow'.format(self.workflow))
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
        pass

    def monitor_portfolios(self):
        """Check holdings of major investment firms such as Berkshire Hathaway"""
        held_tickers = []
        for ticker, investor in investing.conf['following'].items():
            held_tickers += download.holdings(ticker)
        unique = set(held_tickers)
        with open(os.path.join(investing.conf['paths']['save'], 'portfolios.txt'), 'w') as f:
            for ticker in unique:
                f.write('{}\n'.format(ticker))


if __name__ == '__main__':

    parser = argparse.ArgumentParser(
        description='Command line interface for other classes in the investing package',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('workflow', type=str, nargs='?', default='None', help='name of workflow to run')
    parser.add_argument('-b', '--branch', type=str, default='master', help='git branch to run the workflow')
    parser.add_argument('-l', '--list', action='store_true', help='display available workflows and descriptions')
    parser.add_argument('-s', '--save', type=str, default=None, help='local folder to save results in')
    args = parser.parse_args()

    if args.workflow == 'None' and not args.list:
        print('Workflow name must be supplied if --list flag is not used')
        sys.exit(1)
    launcher = Launcher(args.workflow, args.save, args.branch)
    if args.list:
        print('The following workflows are available')
        for w in launcher.workflows:
            doc = launcher.__getattribute__(snakecase(w)).__doc__
            print('  - {}: {}'.format(w, doc))
    else:
        launcher()
