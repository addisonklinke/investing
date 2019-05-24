import logging
from logging.handlers import RotatingFileHandler
import os
from pickle import load
import re

__version__ = '0.1.0'
pkg_dir = os.path.dirname(os.path.realpath(__file__))
save_dir = '/mnt/stocks'
ticker_to_name = load(open('./data/ticker_to_name.pkl', 'rb'))
following = {
    'GFT': 'Bill Gates',
    'AQ': 'Guy Spier',
    'BRK': 'Warren Buffet'}
keys = {
    'alpha-vantage': '26FXSXCVGD0QZZ3M',
    'stock-news': 'uwo11fnch2fuqi5z2nle6aiw9qtt8nmaokixvynk'}
endpoints = {
    'alpha-vantage': 'https://www.alphavantage.co/query',
    'dataroma': 'https://dataroma.com/m/holdings.php',
    'stock-news': 'https://stocknewsapi.com/api/v1'}


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
        formatter = logging.Formatter(
            fmt='%(asctime)s %(name)s %(levelname)8s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S')
        handler = RotatingFileHandler(
            filename=os.path.join(save_dir, '{}.log'.format(__name__)),
            maxBytes=10000000,
            backupCount=4)
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)
        self.logger.setLevel(logging.DEBUG)
        self.logger.info('New {} class initialized'.format(self.name))

