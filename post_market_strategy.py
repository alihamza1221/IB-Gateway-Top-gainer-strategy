import logging
from datetime import datetime
import asyncio
import pytz
import json
import os
from ib_insync import Stock, Order, util
from ib_connection import IBConnectionManager
import config
from ib_insync import ScannerSubscription

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global IB instance - will be set when connecting
ib = None

class PostMarketGainerStrategy:
    """
    Asyncio-based post-market gainer strategy.
    Connects to IB only when entry/exit signals trigger, then disconnects.
    """
    
    def __init__(self, order_quantity=config.ORDER_QUANTITY):
        self.ib_manager = IBConnectionManager()
        self.order_quantity = order_quantity
        self.active_position = None
        self.paper_mode = False
        self.est_tz = pytz.timezone(config.TIMEZONE)
        self.entry_triggered = False
        self.exit_triggered = False
        self.running = False
        self.state_file = 'strategy_state.json'
        
        # Load previous state if exists
        self._load_state()
        
    def _save_state(self):
        """Save active position state to file."""
        try:
            state = {}
            if self.active_position:
                # Serialize position data (excluding non-serializable objects)
                state['active_position'] = {
                    'symbol': self.active_position['symbol'],
                    'quantity': self.active_position['quantity'],
                    'entry_time': self.active_position['entry_time'].isoformat(),
                    'entry_price': self.active_position.get('entry_price')
                }
            else:
                state['active_position'] = None
            
            with open(self.state_file, 'w') as f:
                json.dump(state, f, indent=2)
            logger.debug(f"[STATE] Saved state to {self.state_file}")
        except Exception as e:
            logger.error(f"[STATE] Error saving state: {e}")
    
    def _load_state(self):
        """Load active position state from file."""
        try:
            if os.path.exists(self.state_file):
                with open(self.state_file, 'r') as f:
                    state = json.load(f)
                
                if state.get('active_position'):
                    pos = state['active_position']
                    # Restore position (will recreate contract when needed)
                    self.active_position = {
                        'symbol': pos['symbol'],
                        'quantity': pos['quantity'],
                        'entry_time': datetime.fromisoformat(pos['entry_time']),
                        'entry_price': pos.get('entry_price'),
                        'contract': None,  # Will be recreated when needed
                        'order': None  # Will be recreated when needed
                    }
                    logger.info(f"[STATE] Restored active position: {pos['symbol']} ({pos['quantity']} shares) from {pos['entry_time']}")
                else:
                    logger.info("[STATE] No active position found in saved state")
            else:
                logger.info("[STATE] No previous state file found")
        except Exception as e:
            logger.error(f"[STATE] Error loading state: {e}")
            self.active_position = None
        
    def get_current_est_time(self):
        """Get current time in EST timezone."""
        utc_now = datetime.now(pytz.utc)
        est_now = utc_now.astimezone(self.est_tz)
        return est_now
    
    def is_derivative_security(self, symbol):
        """
        Check if symbol is a warrant, unit, right, or other derivative.
        Returns True if it should be FILTERED OUT.
        """
        symbol_upper = symbol.upper().strip()

        # Warrant patterns (ends with W, WT, WS)
        if symbol_upper.endswith('W'):
            return True
        if symbol_upper.endswith('WT'):
            return True
        if symbol_upper.endswith('WS'):
            return True
        if '.WS' in symbol_upper or '.WT' in symbol_upper:
            return True

        # SPAC Unit patterns (ends with U)
        if symbol_upper.endswith('U'):
            return True
        if symbol_upper.endswith('.U'):
            return True

        # Rights patterns
        if symbol_upper.endswith('R'):
            return True
        if symbol_upper.endswith('.RT'):
            return True

        # Preferred stock patterns
        if '-' in symbol_upper:
            parts = symbol_upper.split('-')
            if len(parts) > 1 and parts[-1] in ['A', 'B', 'C', 'D', 'E', 'PR']:
                return True

        return False


    def get_first_valid_top_gainer(self, scanner_results):
       
        if not scanner_results or len(scanner_results) == 0:
            logger.warning("[FILTER] No scanner results to filter")
            return None

        logger.info(f"[FILTER] Filtering {len(scanner_results)} results for non-derivatives...")

        for i, result in enumerate(scanner_results):
            rank = i + 1
            symbol = result.contractDetails.contract.symbol

            logger.info(f"[FILTER] Rank #{rank}: Checking {symbol}...")

            # Skip if derivative
            if self.is_derivative_security(symbol):
                logger.warning(f"[FILTER] Rank #{rank}: {symbol} is derivative - SKIPPING")
                continue
            
            # Found valid stock - return immediately
            logger.info(f"[FILTER] ✓ FOUND: {symbol} at rank #{rank} (non-derivative)")
            return result

        # All results were derivatives
        logger.error(f"[FILTER] All {len(scanner_results)} results were derivatives")
        return None

    async def get_post_market_top_gainer(self):
        """Fetch the price of the #1 post-market top gainer (async)."""
        global ib
        try:

            logger.info("[SCANNER] Requesting TOP_AFTER_HOURS_PERC_GAIN scanner subscription...")
            #TOP_AFTER_HOURS_PERC_GAIN
            scanner = ScannerSubscription(
                instrument='STK',
                locationCode='STK.US.MAJOR',
                scanCode='TOP_AFTER_HOURS_PERC_GAIN',  
            )

            results = ib.reqScannerSubscription(scanner)
            await asyncio.sleep(8)  # Async sleep to wait for results

            logger.info(f"[SCANNER] Received {len(results)} results")

            if results and len(results) > 0:

                top_gainer = self.get_first_valid_top_gainer(results)

                symbol = top_gainer.contractDetails.contract.symbol

                price = getattr(top_gainer, 'price', None)
                if price is None:
                    contract = top_gainer.contractDetails.contract
                    ticker = ib.reqMktData(contract, '', False, False)
                    await asyncio.sleep(2)  # Async sleep for data to arrive

                    ask_price = ticker.ask
                    bid_price = ticker.bid
                    last_price = ticker.last

                    print(f"[SCANNER] Fetched market data for {symbol}: bid={bid_price}, ask={ask_price}, last={last_price}")
                    
                    # Calculate based on spread
                    limit_price = round(ask_price + ((abs(ask_price - bid_price)) * 2), 2)
                    ib.cancelMktData(contract)

                    price = limit_price


                logger.info(f"Top pre-market gainer: {symbol} Price: {price}")
                return symbol, price
            else:
                logger.warning("[SCANNER] No results returned from scanner")
                return None, None

        except Exception as e:
            logger.error(f"[SCANNER] Error fetching top pre-market gainer: {type(e).__name__}: {e}")
            return None, None

    
    async def execute_long_trade(self, symbol, quantity, price=None):
        """Execute a long (buy) order (async)."""
        global ib
        try:
            
            contract = Stock(symbol, 'SMART', 'USD')
            
            order = Order()
            order.action = 'BUY'
            order.totalQuantity = quantity
            order.orderType = 'LMT'
            order.outsideRth = True
            order.lmtPrice = price
            order.tif = 'GTC'  # Good Till Cancelled
            
            if self.paper_mode:
                logger.info("[ENTRY] Paper mode enabled - skipping trade execution")
                print("[paper] entry - would buy", quantity, "shares of", symbol, "at limit price", price)
                return None
            
            logger.info(f"[TRADE] Placing BUY order for {quantity} shares of {symbol} at limit price {price}...")
            trade = ib.placeOrder(contract, order)
            
            est_time = self.get_current_est_time()
            logger.info(f"✓ ENTRY: BUY {quantity} shares of {symbol} at {est_time} EST")
            logger.info(f"[TRADE] Order status[1]: {trade.orderStatus.status}")

            await asyncio.sleep(20)  # Async sleep
            
    
            logger.info(f"[TRADE] Order status: {trade.orderStatus.status}")
            
            self.active_position = {
                'symbol': symbol,
                'quantity': quantity,
                'entry_time': est_time,
                'entry_price': price,
                'order': trade,
                'contract': contract
            }
            
            # Save state to file
            self._save_state()
            
            return trade
            
        except Exception as e:
            logger.error(f"[TRADE] Error executing long trade: {type(e).__name__}: {e}")
            import traceback
            logger.error(f"[TRADE] Traceback: {traceback.format_exc()}")
            return None
    
    async def close_position(self):
        """Exit the trade - sell all shares (async)."""
        global ib
        try:
            if not self.active_position:
                logger.warning("[TRADE] No active position to close")
                return None
            
            symbol = self.active_position['symbol']
            quantity = self.active_position['quantity']
            
            # Recreate contract if it doesn't exist (e.g., after restart)
            contract = self.active_position.get('contract')
            if contract is None:
                logger.info(f"[TRADE] Recreating contract for {symbol}")
                contract = Stock(symbol, 'SMART', 'USD')
                self.active_position['contract'] = contract
            
            ticker = ib.reqMktData(contract, '', False, False)
            await asyncio.sleep(2)  # Async sleep for data to arrive
            ask_price = ticker.ask
            bid_price = ticker.bid
            last_price = ticker.last
            limit_price = round(bid_price - ((abs(ask_price - bid_price)) * 2), 2)
            print(f"[SCANNER] Fetched market data for {symbol}: bid={bid_price}, ask={ask_price}, last={last_price} , limit price for sell: {limit_price}")

            ib.cancelMktData(contract)
            if bid_price is None:
                logger.error(f"[TRADE] Cannot close position for {symbol} - invalid bid price")
                raise ValueError("Invalid bid price")
            order = Order()
            order.action = 'SELL'
            order.totalQuantity = quantity
            order.orderType = 'LMT'
            order.outsideRth = True
            order.lmtPrice = limit_price
            order.tif = 'GTC'  # Good Till Cancelled

            logger.info(f"[TRADE] Placing SELL order for {quantity} shares of {symbol} at limit price {limit_price}...")
            if self.paper_mode:
                logger.info("[EXIT] Paper mode enabled - skipping trade execution")
                print("[paper]  exit - would sell", quantity, "shares of", symbol)
                return None
            trade = ib.placeOrder(contract, order)
            
            exit_time = self.get_current_est_time()
            entry_time = self.active_position['entry_time']
            hold_duration = exit_time - entry_time
            await asyncio.sleep(10)  # Async sleep

            logger.info(f"\n{'='*60}")
            logger.info(f"✓ EXIT: SELL {quantity} shares of {symbol} at {exit_time} EST")
            logger.info(f"Entry time:  {entry_time}")
            logger.info(f"Exit time:   {exit_time}")
            logger.info(f"Hold duration: {hold_duration}")
            logger.info(f"[TRADE] Order status: {trade.orderStatus.status}")
            logger.info(f"{'='*60}\n")
            
            self.active_position = None
            
            # Save state to file
            self._save_state()
            
            return trade
            
        except Exception as e:
            logger.error(f"[exception found in close_position()] Error closing position: {type(e).__name__}: {e}")
            logger.info("[close_position() exception handler] Retrying to close position...")
            await self.close_position()
                
    
    async def entry_logic(self):
        """Entry signal - connect, execute trade, then disconnect (async)."""
        global ib
       
        est_time = self.get_current_est_time()
        logger.info(f"\n{'='*60}")
        logger.info(f"✓✓✓ ENTRY SIGNAL TRIGGERED at {est_time} EST ✓✓✓")
        logger.info(f"{'='*60}")
        
        # Connect to IB Gateway for this entry signal
        logger.info("[ENTRY] Connecting to IB Gateway...")
        if not await self.ib_manager.connect_async():
            logger.error("[ENTRY] Failed to connect to IB Gateway")
            return
        
        # Set global ib reference
        ib = self.ib_manager.get_ib()
        
        try:
            logger.info("[ENTRY] Fetching post-market top gainer...")
            symbol, price = await self.get_post_market_top_gainer()
            
            if symbol:
                logger.info(f"[ENTRY] Found gainer: {symbol} ({price:.2f})")
                shares = int(self.order_quantity // price)
                print("===shares calculated:", shares)
                await self.execute_long_trade(symbol, shares, price=price)
            else:
                logger.warning("[ENTRY] Skipping entry - no post-market top gainer found")
        finally:
            # Disconnect after entry execution
            logger.info("[ENTRY] Disconnecting from IB Gateway...")
            await self.ib_manager.disconnect_async()
            ib = None
    
    async def exit_logic(self):
        """Exit signal - connect, close position, then disconnect (async)."""
        global ib
        
        est_time = self.get_current_est_time()
        logger.info(f"\n{'='*60}")
        logger.info(f"✓✓✓ EXIT SIGNAL TRIGGERED at {est_time} EST ✓✓✓")
        logger.info(f"{'='*60}")
        
        # Connect to IB Gateway for this exit signal
        logger.info("[EXIT] Connecting to IB Gateway...")
        if not await self.ib_manager.connect_async():
            logger.error("[EXIT] Failed to connect to IB Gateway")
            return
        
        # Set global ib reference
        ib = self.ib_manager.get_ib()
        
        try:
            await self.close_position()
        finally:
            # Disconnect after exit execution
            logger.info("[EXIT] Disconnecting from IB Gateway...")
            await self.ib_manager.disconnect_async()
            ib = None
    
    async def check_and_trigger_async(self):
        """
        Async scheduler - checks time and executes trade logic.
        """
        est_now = self.get_current_est_time()
        current_hour = est_now.hour
        current_minute = est_now.minute
        current_second = est_now.second
        current_weekday = est_now.weekday()
        
        # Check ENTRY
        if (current_weekday == config.ENTRY_DAY and 
            current_hour == config.ENTRY_TIME_HOUR and 
            current_minute == config.ENTRY_TIME_MINUTE and
            current_second == config.ENTRY_TIME_SECOND and
            not self.entry_triggered):
            logger.info(f"[SCHEDULER] Entry time matched! {current_hour:02d}:{current_minute:02d}:{current_second:02d}")
            self.entry_triggered = True
            await self.entry_logic()  # Execute directly in async context
            return
        
        if current_minute != config.ENTRY_TIME_MINUTE:
            self.entry_triggered = False
        
        # Check EXIT
        if (current_weekday == config.EXIT_DAY and 
            current_hour == config.EXIT_TIME_HOUR and 
            current_minute == config.EXIT_TIME_MINUTE and
            current_second == config.EXIT_TIME_SECOND and
            not self.exit_triggered):
            logger.info(f"[SCHEDULER] Exit time matched! {current_hour:02d}:{current_minute:02d}:{current_second:02d}")
            self.exit_triggered = True
            await self.exit_logic()  # Execute directly in async context
            return
        
        if current_minute != config.EXIT_TIME_MINUTE:
            self.exit_triggered = False
    
    async def start_async(self):
        """Start the strategy - connects to IB only when signals trigger."""
        logger.info("\n" + "="*60)
        logger.info("Starting Post-Market Gainer Strategy (Asyncio - On-Demand Connection)")
        logger.info("="*60)
        logger.info(f"Timezone: {config.TIMEZONE} (EST/EDT)")
        logger.info(f"Order quantity: ${config.ORDER_QUANTITY}")
        logger.info(f"\nENTRY:  {['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'][config.ENTRY_DAY]}  {config.ENTRY_TIME_HOUR:02d}:{config.ENTRY_TIME_MINUTE:02d}:{config.ENTRY_TIME_SECOND:02d} EST")
        logger.info(f"EXIT:   {['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'][config.EXIT_DAY]}  {config.EXIT_TIME_HOUR:02d}:{config.EXIT_TIME_MINUTE:02d}:{config.EXIT_TIME_SECOND:02d} EST")
        logger.info("="*60 + "\n")
        
        est_time = self.get_current_est_time()
        logger.info(f"Current EST time: {est_time}")
        logger.info("Strategy running. Will connect to IB only when entry/exit signals trigger...\n")
        
        self.running = True
        
        try:
            while self.running:
                # Check for scheduled times and execute logic
                # Connection happens inside entry_logic() and exit_logic()
                await self.check_and_trigger_async()
                
                await asyncio.sleep(0.5)  # Async sleep
                
        except KeyboardInterrupt:
            logger.info("\nStopping strategy...")
            if self.active_position:
                logger.warning("WARNING: Closing strategy with active position!")
        except Exception as e:
            logger.error(f"[MAIN] Unexpected error: {e}")
            import traceback
            logger.error(traceback.format_exc())

