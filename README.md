# investing
Automated scripts for monitoring long-term stock trends 

## Author

Addison Klinke

## Installation

1. Clone this repository
2. Install the Python requirements
3. Create a symlink from the repository's root folder to your Python path

```bash
git clone https://github.com/addisonklinke/investing.git
cd investing
pip install requirements.txt
sudo ln -s /path/to/investing /path/on/python/path
```

## Configuration

Default configuration values are located in the file 
`config/investing.conf.defaults`. To override, create a new file called 
`config/investing.conf` and populate it according the default template. Any 
values from the user-created config file will take precedence over the default 
config file at runtime. 
