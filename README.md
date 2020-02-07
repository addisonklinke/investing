# investing
Automated scripts for monitoring long-term stock trends 

## Author

Addison Klinke

## Installation

1. Clone this repository `git clone https://github.com/addisonklinke/investing.git`
2. Install the Python requirements `pip install - rrequirements.txt

## Usage

The launcher script provides the primary interface for running different workflows. 
To familiarize yourself with the available options, run `python launcher.py --list`

## Configuration

Default configuration values are located in the file 
`config/investing.conf.defaults`. To override, create a new file called 
`config/investing.conf` and populate it according the default template. Any 
values from the user-created config file will take precedence over the default 
config file at runtime. 
