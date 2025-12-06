import logging
from post_market_strategy import PostMarketGainerStrategy
import config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    # Initialize strategy with global order quantity
    strategy = PostMarketGainerStrategy(order_quantity=config.ORDER_QUANTITY)
    
    # Start the strategy (runs indefinitely with scheduler)
    strategy.start()

if __name__ == '__main__':
    main()


