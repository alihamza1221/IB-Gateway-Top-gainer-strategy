# Global Trading Configuration
ORDER_QUANTITY = 100
TIMEZONE = 'US/Eastern'  

# ENTRY: Friday pre-market
ENTRY_DAY = 4  # moday for testing (4=Friday)
ENTRY_TIME_HOUR = 18
ENTRY_TIME_MINUTE = 58
ENTRY_TIME_SECOND = 45

# EXIT: Monday Morning
EXIT_DAY = 0 # Monday (0=Monday)
EXIT_TIME_HOUR = 4
EXIT_TIME_MINUTE = 1
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
