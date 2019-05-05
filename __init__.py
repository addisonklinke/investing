from pickle import load

keys = {
    'alpha-vantage': '26FXSXCVGD0QZZ3M',
    'whale-wisdom': 'oaHbKtuUdWkcXCsw5jk4'}
ticker_to_name = load(open('./data/ticker_to_name.pkl', 'rb'))
