import logging
from logging.handlers import RotatingFileHandler
import os
from pickle import load
import re
import yaml

# Package metadata
__version__ = '0.1.0'

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

# Details for APIs used in this package
endpoints = {
    'alpha-vantage': 'https://www.alphavantage.co/query',
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
