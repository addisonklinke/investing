from pickle import load

keys = {
    'alpha-vantage': '26FXSXCVGD0QZZ3M',
    'stock-news': 'uwo11fnch2fuqi5z2nle6aiw9qtt8nmaokixvynk'}
ticker_to_name = load(open('./data/ticker_to_name.pkl', 'rb'))
endpoints = {
    'alpha-vantage': 'https://www.alphavantage.co/query',
    'dataroma': 'https://dataroma.com/m/holdings.php',
    'stock-news': 'https://stocknewsapi.com/api/v1'}
