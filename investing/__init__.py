import logging
from logging.handlers import RotatingFileHandler
import os
import re
import warnings
import yaml
from .exceptions import ImproperlyConfigured

# Package metadata
__version__ = '0.2.0'

# Simplify warning format to a single line
warnings.formatwarning = lambda message, category, filename, lineno, line=None: \
    f'{filename}:{lineno}: {category.__name__}: {message}\n'

# Load config files and override defaults with user values
with open('./config/investing.defaults.yaml', 'r') as stream:
    defaults = yaml.load(stream, Loader=yaml.FullLoader)
user_path = os.path.realpath('./config/investing.yaml')
if os.path.exists(user_path):
    with open(user_path, 'r') as stream:
        user = yaml.load(stream, Loader=yaml.FullLoader)
    conf = {**defaults, **user}
else:
    conf = defaults

# Validate configuration
if not os.path.isdir(conf['paths']['save']):
    raise ImproperlyConfigured(f'Save directory {conf["paths"]["save"]} does not exist')
for api, key in conf['keys'].items():
    if key is None:
        raise ImproperlyConfigured(f'No API key configured for {api}')
for i, p in enumerate(conf['portfolios'], 1):
    if 'name' not in p:
        raise ImproperlyConfigured(f'Portfolio {i} must be named')
    portfolio_type = p.get('type')
    if portfolio_type not in ['follow', 'manual']:
        raise ImproperlyConfigured(f'Unknown type {portfolio_type} for {p["name"]} portfolio')
    if len(p.get('symbols', [])) == 0:
        raise ImproperlyConfigured(f'Portfolio {p["name"]} has no symbols defined')

# Details for APIs used in this package
conf['endpoints'] = {
    'alpha_vantage': 'https://www.alphavantage.co/query',
    'dataroma': 'https://dataroma.com/m/holdings.php',
    'finnhub': {
        'sentiment': 'https://finnhub.io/api/v1/news-sentiment',
        'news': 'https://finnhub.io/api/v1/news'}}


class InvestingLogging:
    """Base class for logging across the entire package.

    All classes in other (sub)modules of this package should derive from this
    class. Each class is setup with a uniquely named logger, but all point to
    the same log file. Then, any logging can be handled using the ``logger``
    attribute's methods.
    """

    def __init__(self):
        self.name = type(self).__name__
        try:
            class_str = re.compile('(?<=\').+(?=\')').findall(str(self.__class__))[0]
            self.module = re.compile('(?<=\.).*$').findall(class_str)[0]
        except IndexError:
            self.module = 'investing'
        if self.module == 'Launcher':
            self.module = 'workflows.Launcher'
        self.logger = logging.getLogger(self.module)
        self.logger.propagate = False
        self.formatter = logging.Formatter(
            fmt='%(asctime)s %(name)s %(levelname)8s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S')
        handler = RotatingFileHandler(
            filename=os.path.join(conf['paths']['save'], '{}.log'.format(__name__)),
            maxBytes=10000000,
            backupCount=4)
        handler.setFormatter(self.formatter)
        self.logger.addHandler(handler)
        self.logger.setLevel(logging.DEBUG)
        self.logger.info('New {} class initialized'.format(self.name))
