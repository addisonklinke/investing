from pickle import load

keys = {
    'alpha-vantage': '26FXSXCVGD0QZZ3M',
    'whale-wisdom': {
        'shared': 'oaHbKtuUdWkcXCsw5jk4',
        'secret': 's0zpLNkpI7GBKz2chiABMJv97eGNdIyQyjohrHQh'},
    'stock-news': 'uwo11fnch2fuqi5z2nle6aiw9qtt8nmaokixvynk'}
ticker_to_name = load(open('./data/ticker_to_name.pkl', 'rb'))
endpoints = {
    'whale-wisdom': 'https://whalewisdom.com/shell/command.json?args={}&api_shared_key={}&api_sig={}&timestamp={}',
    'stock-news': 'https://stocknewsapi.com'}
