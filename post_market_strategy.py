import logging
from datetime import datetime, time
import threading
import pytz
from ib_insync import Stock, Order, IB
from ib_connection import IBConnectionManager
import config
from ib_insync import ScannerSubscription
import time
from ib_insync import Contract
import yfinance as yf

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class PreMarketGainerStrategy:
    """
    Pre-market gainer strategy with proper threading support.
    IB operations run in main thread, scheduler runs in background.
    """
    
    def __init__(self, order_quantity=config.ORDER_QUANTITY):
        self.ib_manager = IBConnectionManager()
        self.ib_manager.connect()
        self.order_quantity = order_quantity
        self.active_position = None
        self.paper_mode = True
        self.est_tz = pytz.timezone(config.TIMEZONE)
        self.entry_triggered = False
        self.exit_triggered = False
        
        # Queue for scheduler to signal main thread
        self.entry_signal = threading.Event()
        self.exit_signal = threading.Event()
        
    def get_current_est_time(self):
        """Get current time in EST timezone."""
        utc_now = datetime.now(pytz.utc)
        est_now = utc_now.astimezone(self.est_tz)
        return est_now
    
    def get_pre_market_top_gainer(self):
        """Fetch the price of the #1 pre-market top gainer."""
        try:
            ib = self.ib_manager.get_ib()

            logger.info("[SCANNER] Requesting TOP_PERC_GAIN_AFTER_OPEN scanner subscription...")

            scanner = ScannerSubscription(
                instrument='STK',
                locationCode='STK.US.MAJOR',
                scanCode='TOP_AFTER_HOURS_PERC_GAIN'  
            )

            results = ib.reqScannerSubscription(scanner)
            ib.sleep(3)  # Wait for results to arrive

            logger.info(f"[SCANNER] Received {len(results)} results")

            if results and len(results) > 0:
                top_gainer = results[0]
                symbol = top_gainer.contractDetails.contract.symbol

                price = getattr(top_gainer, 'price', None)
                if price is None:
                    contract = top_gainer.contractDetails.contract
                    ticker = yf.Ticker(symbol)
                    current_price = ticker.info['regularMarketPrice']

                    # Request live market data for the contract
                    #market_data = ib.reqMktData(contract, '', True, False)
                    ib.sleep(2)
                    #price = market_data.last
                    price = current_price


                logger.info(f"Top pre-market gainer: {symbol} Price: {price}")
                return symbol, price
            else:
                logger.warning("[SCANNER] No results returned from scanner")
                return None, None

        except Exception as e:
            logger.error(f"[SCANNER] Error fetching top pre-market gainer: {type(e).__name__}: {e}")
            return None, None

    
    def execute_long_trade(self, symbol, quantity):
        """Execute a long (buy) order."""
        try:
            ib = self.ib_manager.get_ib()
            
            contract = Stock(symbol, 'SMART', 'USD')
            
            order = Order()
            order.action = 'BUY'
            order.totalQuantity = quantity
            order.orderType = 'MKT'
            
            if self.paper_mode:
                logger.info("[ENTRY] Paper mode enabled - skipping trade execution")
                print("[paper] entry - would buy", quantity, "shares of", symbol)
                return None
            
            logger.info(f"[TRADE] Placing BUY order for {quantity} shares of {symbol}...")
            trade = ib.placeOrder(contract, order)
            
            est_time = self.get_current_est_time()
            logger.info(f"✓ ENTRY: BUY {quantity} shares of {symbol} at {est_time} EST")
            logger.info(f"[TRADE] Order status: {trade.orderStatus.status}")
            
            self.active_position = {
                'symbol': symbol,
                'quantity': quantity,
                'entry_time': est_time,
                'order': trade,
                'contract': contract
            }
            
            return trade
            
        except Exception as e:
            logger.error(f"[TRADE] Error executing long trade: {type(e).__name__}: {e}")
            import traceback
            logger.error(f"[TRADE] Traceback: {traceback.format_exc()}")
            return None
    
    def close_position(self):
        """Exit the trade - sell all shares."""
        try:
            if not self.active_position:
                logger.warning("[TRADE] No active position to close")
                return None
            
            ib = self.ib_manager.get_ib()
            
            symbol = self.active_position['symbol']
            quantity = self.active_position['quantity']
            contract = self.active_position['contract']
            
            if self.paper_mode:
                logger.info("[EXIT] Paper mode enabled - skipping trade execution")
                print("[paper]  exit - would sell", quantity, "shares of", symbol)
                return None

            order = Order()
            order.action = 'SELL'
            order.totalQuantity = quantity
            order.orderType = 'MKT'
            
            logger.info(f"[TRADE] Placing SELL order for {quantity} shares of {symbol}...")
            trade = ib.placeOrder(contract, order)
            
            exit_time = self.get_current_est_time()
            entry_time = self.active_position['entry_time']
            hold_duration = exit_time - entry_time
            
            logger.info(f"\n{'='*60}")
            logger.info(f"✓ EXIT: SELL {quantity} shares of {symbol} at {exit_time} EST")
            logger.info(f"Entry time:  {entry_time}")
            logger.info(f"Exit time:   {exit_time}")
            logger.info(f"Hold duration: {hold_duration}")
            logger.info(f"[TRADE] Order status: {trade.orderStatus.status}")
            logger.info(f"{'='*60}\n")
            
            self.active_position = None
            
            return trade
            
        except Exception as e:
            logger.error(f"[TRADE] Error closing position: {type(e).__name__}: {e}")
            import traceback
            logger.error(f"[TRADE] Traceback: {traceback.format_exc()}")
            return None
    
    def entry_logic(self):
        """Entry signal - execute at scheduled time."""
       
        est_time = self.get_current_est_time()
        logger.info(f"\n{'='*60}")
        logger.info(f"✓✓✓ ENTRY SIGNAL TRIGGERED at {est_time} EST ✓✓✓")
        logger.info(f"{'='*60}")
        
        if not self.ib_manager.ensure_connected():
            logger.error("[ENTRY] Cannot execute trade - no connection to IB Gateway")
            return
        
        logger.info("[ENTRY] Fetching pre-market top gainer...")
        symbol, price = self.get_pre_market_top_gainer()
        
        if symbol:
            logger.info(f"[ENTRY] Found gainer: {symbol} ({price:.2f})")
            shares = int(self.order_quantity // price)
            self.execute_long_trade(symbol, shares)
        else:
            logger.warning("[ENTRY] Skipping entry - no pre-market top gainer found")
    
    def exit_logic(self):
        """Exit signal - execute at scheduled time."""
        est_time = self.get_current_est_time()
        logger.info(f"\n{'='*60}")
        logger.info(f"✓✓✓ EXIT SIGNAL TRIGGERED at {est_time} EST ✓✓✓")
        logger.info(f"{'='*60}")
        
        if not self.ib_manager.ensure_connected():
            logger.error("[EXIT] Cannot execute trade - no connection to IB Gateway")
            return
        
        self.close_position()
    
    def check_and_trigger(self):
        """
        Background scheduler thread - just checks time, doesn't execute IB operations.
        Signals main thread when it's time to trade.
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
            self.entry_signal.set()  # Signal main thread
            self.entry_triggered = True
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
            self.exit_signal.set()  # Signal main thread
            self.exit_triggered = True
            return
        
        if current_minute != config.EXIT_TIME_MINUTE:
            self.exit_triggered = False
    
    def run_scheduler(self):
        """Background scheduler - only checks time, doesn't call IB API."""
        logger.info("[SCHEDULER] Background scheduler thread started")
        
        while True:
            try:
                self.check_and_trigger()
                time.sleep(1)
            except Exception as e:
                logger.error(f"[SCHEDULER] Error in scheduler: {e}")
                time.sleep(1)
    
    def start(self):
        """Start the strategy - IB operations run in main thread."""
        logger.info("\n" + "="*60)
        logger.info("Starting Pre-Market Gainer Strategy")
        logger.info("="*60)
        logger.info(f"Timezone: {config.TIMEZONE} (EST/EDT)")
        logger.info(f"Order quantity: {config.ORDER_QUANTITY} shares")
        logger.info(f"\nENTRY:  {['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'][config.ENTRY_DAY]}  {config.ENTRY_TIME_HOUR:02d}:{config.ENTRY_TIME_MINUTE:02d}:{config.ENTRY_TIME_SECOND:02d} EST")
        logger.info(f"EXIT:   {['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'][config.EXIT_DAY]}  {config.EXIT_TIME_HOUR:02d}:{config.EXIT_TIME_MINUTE:02d}:{config.EXIT_TIME_SECOND:02d} EST")
        logger.info("="*60 + "\n")
        
        # Start background scheduler thread
        scheduler_thread = threading.Thread(target=self.run_scheduler, daemon=True)
        scheduler_thread.start()
        
        est_time = self.get_current_est_time()
        logger.info(f"Current EST time: {est_time}")
        logger.info("Strategy running. Waiting for scheduled times...\n")
        
        try:
            while True:
                # Main thread checks for signals from scheduler
                if self.entry_signal.is_set():
                    logger.info("[MAIN] Entry signal received, executing in main thread...")
                    self.entry_signal.clear()
                    self.entry_logic()
                
                if self.exit_signal.is_set():
                    logger.info("[MAIN] Exit signal received, executing in main thread...")
                    self.exit_signal.clear()
                    self.exit_logic()
                
                # Keep connection alive
                self.ib_manager.ensure_connected()
                
                time.sleep(0.5)
                
        except KeyboardInterrupt:
            logger.info("\nStopping strategy...")
            if self.active_position:
                logger.warning("WARNING: Closing strategy with active position!")
            self.ib_manager.disconnect()

