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

## Disclaimer

Use at your own risk.
Per the MIT license, this project does not provide *ANY* guarantees of proper functionality.
Users should not make investment decisions without consulting a reliable, external source of 
information such as a professional financial planner.
