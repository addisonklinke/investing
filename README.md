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

Default configuration values are located in the file 
`config/investing.defaults.yaml`. To override, create a new file called 
`config/investing.yaml` and populate it according the default template. Any 
values from the user-created config file will take precedence over the default 
config file at runtime. 

You will need (free) accounts with the following websites to populate the API key fields

* [Finnhub](https://finnhub.io/register)
* [Alpha Vantage](https://www.alphavantage.co/support/#api-key) 
