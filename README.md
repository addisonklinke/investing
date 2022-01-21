# investing
Automated scripts for monitoring long-term stock trends 

## Installation

1. Clone this repository
2. Install the Python requirements
3. Run unit tests

```bash
git clone https://github.com/addisonklinke/investing.git
cd investing
pip install - r requirements.txt
python -m unittest discover -v
```

## Configuration

Default configuration values are located in the file `config/investing.defaults.yaml`. 
To get started, run `python launcher.py configure` and follow the prompts.
This will populate a new file called `config/investing.yaml`. 
Any values from the user-created config will take precedence over the default config at runtime. 

You will need (free) accounts with the following websites to populate the API key fields

* [Alpha Vantage](https://www.alphavantage.co/support/#api-key): 20-year historical ticker prices
* [Finnhub](https://finnhub.io/register): alternative news and sentiment data
* [Metals API](https://metals-api.com/pricing): precious metals and foreign currencies

Currently, there is not a free API that can provide 20+ year historical data on gold prices.
The best option as of this writing appears to be the Metals API listed above which can return a 5-day
history (limited to 50 calls/month).
Fortunately, the [World Gold Council](https://www.gold.org/goldhub/data/gold-prices) provides an XLSX file
with daily prices going back to 1979.

By manually extracting the date and price columns from their "Daily" tab, you can save this under `xau.csv`
in your configured save path.
This will serve as a starting point which the Metals API can continue adding to automatically as time goes on.
After saving the CSV, load and save it once through this package's `Ticker` class in order to apply consistent formatting

```python
from investing.data import Ticker

xau = Ticker('xau')
xau.data.to_csv(xau.csv_path)
```

## Usage

The launcher script provides the primary interface for running different workflows.
To familiarize yourself with the available options, run `python launcher.py -h`

A typical sequence of commands would be

1. Configure a few different `portfolios` of tickers in the YAML file created above
2. Automate a cron job for `python launcher.py daily_tickers`. This will keep your local CSVs in-sync
3. Manually run the `compare_performance` or `expected_return` workflows for your own research

## Disclaimer

Use at your own risk.
Per the MIT license, this project does not provide *ANY* guarantees of proper functionality.
Users should not make investment decisions without consulting a reliable, external source of 
information such as a professional financial planner.
