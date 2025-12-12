# Global Trading Configuration
ORDER_QUANTITY = 0 # refers to $ amount per trade
TIMEZONE = 'US/Eastern'  

# ENTRY: Friday pre-market
#0 = Monday, 1=Tuesday, 2=Wednesday, 3=Thursday, 4=Friday, 5=Saturday, 6=Sunday
ENTRY_DAY = 4  # (4=Friday)
ENTRY_TIME_HOUR = 5
ENTRY_TIME_MINUTE = 26
ENTRY_TIME_SECOND = 0

# EXIT: Monday Morning
EXIT_DAY = 4 # Monday (0=Monday)
EXIT_TIME_HOUR = 5
EXIT_TIME_MINUTE = 30
EXIT_TIME_SECOND = 0

# IB Gateway Connection
IB_HOST = '127.0.0.1'
IB_PORT = 4002
IB_CLIENT_ID = 1
RECONNECT_INTERVAL = 5  # seconds
MAX_RETRIES = 10

# Logging
LOG_LEVEL = 'INFO'
LOG_FILE = 'trading_strategy.log'
