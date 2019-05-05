from pickle import load

keys = {
    'alpha-vantage': '26FXSXCVGD0QZZ3M',
    'whale-wisdom': {
        'shared': 'oaHbKtuUdWkcXCsw5jk4',
        'secret': 's0zpLNkpI7GBKz2chiABMJv97eGNdIyQyjohrHQh'}}
ticker_to_name = load(open('./data/ticker_to_name.pkl', 'rb'))
