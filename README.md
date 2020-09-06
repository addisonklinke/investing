# investing
Automated scripts for monitoring long-term stock trends 

## Author

Addison Klinke

## Installation

1. Clone this repository `git clone https://github.com/addisonklinke/investing.git`
2. Install the Python requirements `pip install - r requirements.txt`

## Usage

The launcher script provides the primary interface for running different workflows. 
To familiarize yourself with the available options, run `python launcher.py -h`

## Configuration

Default configuration values are located in the file `config/investing.defaults.yaml`. 
To get started, run `python launcher.py configure` and follow the prompts.
This will populate a new file called `config/investing.yaml`. 
Any values from the user-created config will take precedence over the default config at runtime. 

You will need (free) accounts with the following websites to populate the API key fields

* [Finnhub](https://finnhub.io/register)
* [Alpha Vantage](https://www.alphavantage.co/support/#api-key)
* [Metals API](https://metals-api.com/pricing)

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

## Disclaimer

Use at your own risk.
Per the MIT license, this project does not provide *ANY* guarantees of proper functionality.
Users should not make investment decisions without consulting a reliable, external source of 
information such as a professional financial planner.
