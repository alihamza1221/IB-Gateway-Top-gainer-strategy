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
            
    def _on_error(self, reqId, errorCode, errorString, contract):
        """
        Error callback to catch connection errors.
        """
        
        # Update last error code
        self.last_error_code = errorCode
        
        # Connection lost errors
        if errorCode in [1100, 1300, 2110]:
            logger.error(f"***_on_error {errorCode}] Connection lost: {errorString} reconnecting [True]")
            if self.ib: 
                logger.info(" _on_error() :: Will call connect()...")
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
                if self.ib is not None and self.ensure_connected() is False:
                    try:
                        logger.info(" connect() :: Cleaning up old connection...")
                        # Remove event handlers before disconnect
                        self.ib.errorEvent.clear()
                        self.ib.disconnectedEvent.clear()
                        self.ib.disconnect()
                        
                    except Exception as cleanup_error:
                        logger.warning(f"[CONN] Cleanup error (ignored): {cleanup_error}")
                    
                    time.sleep(3)
                
                # Create NEW IB instance (prevents duplicate event handlers)
                logger.info(" connect() :: Creating new IB instance...")
                if self.ib is not None:
                    del self.ib
                self.ib = IB()
                
                # Register event handlers on the NEW instance
                self.ib.errorEvent += self._on_error
                self.ib.disconnectedEvent += self._on_disconnected
                
                # Attempt connection
                logger.info(f" connect() :: Attempting to connect to IB Gateway at {self.host}:{self.port} (attempt {retries + 1}/{self.max_retries})...")
                self.ib.connect(self.host, self.port, clientId=self.client_id, timeout=20)
                
                # Wait for connection to stabilize
                self.ib.sleep(10)
                
                # Verify connection with test request
                if self._test_connection():
                    logger.info(" connect() :: ✓ Connected to IB Gateway successfully")
                    self.is_connected = True
                    self.connection_lost = False
                    self.reconnecting = False
                    self.last_error_code = None
                    return True
                else:
                    logger.warning(" connect() :: Connection test failed")
                    retries += 1
                    
            except Exception as e:
                retries += 1
                logger.warning(f" connect() :: Connection failed (attempt {retries}/{self.max_retries}): {e}")
                
                if retries < self.max_retries:
                    logger.info(f" connect() :: Retrying in {self.reconnect_interval} seconds...")
                    time.sleep(self.reconnect_interval)
        
        logger.error(" connect() :: Failed to connect after max retries")
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
            self.ib.sleep(5)
            
            if server_time is not None:
                logger.debug(f"[TEST] Server time: {server_time}")
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
            logger.warning("ensure_connected(1) :: No IB instance, connecting...")
            return False
        
        # Check 2: Socket not connected
        if not self.ib.isConnected():
            logger.warning("ensure_connected(2) :: Socket not connected, reconnecting...")
            return False
        
        if not self._test_connection():
            logger.warning("ensure_connected(3) :: Connection test failed, reconnecting...")
            return False
                
        # Connection appears healthy
        return True
    
    def get_ib(self):
        """Return IB instance, ensuring it's connected."""
        if not self.ensure_connected():
            self.connect()
        return self.ib
    
    def disconnect(self):
        """Gracefully disconnect from IB Gateway."""
        try:
            if self.ib and self.ensure_connected() is False:
                # Clear event handlers                    
                self.ib.errorEvent.clear()
                self.ib.disconnectedEvent.clear()
                
                # Disconnect
                self.ib.disconnect()
                
                
                time.sleep(10)
                
                
            self.is_connected = False
            self.connection_lost = False
            logger.info(" disconnect ():: Disconnected from IB Gateway")
            
        except Exception as e:
            logger.error(f" disconnect ():: Error disconnecting: {e}")