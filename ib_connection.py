import logging
import time
from datetime import datetime
from ib_insync import IB

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class IBConnectionManager:
    """
    Handles robust IB Gateway connection with automatic reconnection.
    Reinitializes IB() on each reconnect to avoid duplicate event handlers.
    """
    
    def __init__(self, host='127.0.0.1', port=4002, client_id=0, reconnect_interval=5, max_retries=10):
        self.host = host
        self.port = port
        self.client_id = client_id
        self.reconnect_interval = reconnect_interval
        self.max_retries = max_retries
        
        # Initialize state
        self.ib = None
        self.is_connected = False
        self.connection_lost = False
        self.last_error_code = None
        self.reconnecting = False  # Track if we're in reconnect mode
        
        # Initial connection
        self.connect()
    
    def _on_error(self, reqId, errorCode, errorString, contract):
        """
        Error callback to catch connection errors.
        """
        logger.warning(f"[IB ERROR] reqId={reqId}, code={errorCode}, msg={errorString}")
        
        # Update last error code
        self.last_error_code = errorCode
        
        # Connection lost errors
        if errorCode in [1100, 1300, 2110]:
            logger.error(f"[ERROR {errorCode}] Connection lost: {errorString}")
            self.connection_lost = True
            self.is_connected = False
            
            # For error 1300 (API disabled), trigger reconnect
            if errorCode == 1300:
                logger.warning("[ERROR 1300] API disabled, will attempt reconnect...")
                self.reconnecting = True
                if self.ib and self.ib.isConnected():
                    self.ib.disconnect()
            
        # Connection restored errors
        elif errorCode in [1101, 1102, 2104]:
            logger.info(f"[ERROR {errorCode}] Connection restored: {errorString}")
            
            # For 1102, force reconnect to refresh connection
            if errorCode == 1102:
                logger.warning("[ERROR 1102] Market data farm reconnected - refreshing connection...")
                self.reconnecting = True
                if self.ib and self.ib.isConnected():
                    self.ib.disconnect()
            else:
                self.connection_lost = False
                self.is_connected = True
        
        # Critical connection errors
        elif errorCode in [502, 504, 10053]:
            logger.error(f"[ERROR {errorCode}] Critical error: {errorString}")
            self.connection_lost = True
            self.is_connected = False
    
    def _on_disconnected(self):
        """
        Callback when connection is disconnected.
        """
        logger.warning("[DISCONNECTED] Connection to IB Gateway lost")
        self.is_connected = False
        self.connection_lost = True
        
        # Only auto-reconnect if we're in reconnecting mode or if this was unexpected
        if self.reconnecting or self.is_connected:
            logger.info("[DISCONNECTED] Attempting to reconnect...")
            time.sleep(2)
            self.connect()
    
    def connect(self):
        """
        Establish connection to IB Gateway with retry logic.
        Creates a NEW IB() instance to avoid duplicate event handlers.
        """
        retries = 0
        
        while retries < self.max_retries:
            try:
                # Clean up old connection if exists
                if self.ib is not None:
                    try:
                        logger.info("[CONN] Cleaning up old connection...")
                        # Remove event handlers before disconnect
                        if hasattr(self.ib, 'errorEvent'):
                            self.ib.errorEvent.clear()
                        if hasattr(self.ib, 'disconnectedEvent'):
                            self.ib.disconnectedEvent.clear()
                        
                        if self.ib.isConnected():
                            self.ib.disconnect()
                    except Exception as cleanup_error:
                        logger.warning(f"[CONN] Cleanup error (ignored): {cleanup_error}")
                    
                    time.sleep(1)
                
                # Create NEW IB instance (prevents duplicate event handlers)
                logger.info("[CONN] Creating new IB instance...")
                self.ib = IB()
                
                # Register event handlers on the NEW instance
                self.ib.errorEvent += self._on_error
                self.ib.disconnectedEvent += self._on_disconnected
                
                # Attempt connection
                logger.info(f"[CONN] Attempting to connect to IB Gateway at {self.host}:{self.port} (attempt {retries + 1}/{self.max_retries})...")
                self.ib.connect(self.host, self.port, clientId=self.client_id, timeout=20)
                
                # Wait for connection to stabilize
                self.ib.sleep(2)
                
                # Verify connection with test request
                if self._test_connection():
                    logger.info("[CONN] ✓ Connected to IB Gateway successfully")
                    self.is_connected = True
                    self.connection_lost = False
                    self.reconnecting = False
                    self.last_error_code = None
                    return True
                else:
                    logger.warning("[CONN] Connection test failed")
                    retries += 1
                    
            except Exception as e:
                retries += 1
                logger.warning(f"[CONN] Connection failed (attempt {retries}/{self.max_retries}): {e}")
                
                if retries < self.max_retries:
                    logger.info(f"[CONN] Retrying in {self.reconnect_interval} seconds...")
                    time.sleep(self.reconnect_interval)
        
        logger.error("[CONN] Failed to connect after max retries")
        self.is_connected = False
        self.connection_lost = True
        return False
    
    def _test_connection(self):
        """
        Actively test if connection is working.
        """
        try:
            if not self.ib or not self.ib.isConnected():
                return False
            
            # Request current time as health check
            server_time = self.ib.reqCurrentTime()
            self.ib.sleep(1)
            
            if server_time and server_time > 0:
                logger.debug(f"[TEST] Server time: {datetime.fromtimestamp(server_time)}")
                return True
            else:
                logger.warning("[TEST] Invalid server time response")
                return False
                
        except Exception as e:
            logger.error(f"[TEST] Connection test failed: {e}")
            return False
    
    def ensure_connected(self):
        """
        Check connection health and reconnect if necessary.
        """
        # Check 1: No IB instance
        if self.ib is None:
            logger.warning("[HEALTH] No IB instance, connecting...")
            return self.connect()
        
        # Check 2: Socket not connected
        if not self.ib.isConnected():
            logger.warning("[HEALTH] Socket not connected, reconnecting...")
            return self.connect()
        
        # Check 3: Connection lost flag from error handler
        if self.connection_lost:
            logger.warning("[HEALTH] Connection lost flag set, reconnecting...")
            return self.connect()
        
        # Check 4: Critical error codes
        if self.last_error_code in [1100, 1300, 2110, 502, 504, 10053]:
            logger.warning(f"[HEALTH] Critical error code {self.last_error_code}, reconnecting...")
            return self.connect()
        
        # Connection appears healthy
        return True
    
    def get_ib(self):
        """Return IB instance, ensuring it's connected."""
        if not self.ensure_connected():
            raise ConnectionError("Failed to establish IB connection")
        return self.ib
    
    def disconnect(self):
        """Gracefully disconnect from IB Gateway."""
        try:
            self.reconnecting = False  # Prevent auto-reconnect
            
            if self.ib:
                # Clear event handlers
                if hasattr(self.ib, 'errorEvent'):
                    self.ib.errorEvent.clear()
                if hasattr(self.ib, 'disconnectedEvent'):
                    self.ib.disconnectedEvent.clear()
                
                # Disconnect
                self.ib.disconnect()
                
            self.is_connected = False
            self.connection_lost = False
            logger.info("[CONN] Disconnected from IB Gateway")
            
        except Exception as e:
            logger.error(f"[CONN] Error disconnecting: {e}")
