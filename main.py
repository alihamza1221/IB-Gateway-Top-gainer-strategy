import logging
from post_market_strategy import PostMarketGainerStrategy
import config
import asyncio
from ib_insync import util

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def main():
    """Main async entry point for the strategy."""
    logger.info("[MAIN] Initializing Post-Market Gainer Strategy...")
    
    # Initialize strategy
    strategy = PostMarketGainerStrategy(order_quantity=config.ORDER_QUANTITY)
    
    # Start the strategy (runs asynchronously)
    await strategy.start_async()

if __name__ == "__main__":
    # Use ib_insync's util.run for proper event loop management with IB
    util.run(main())

