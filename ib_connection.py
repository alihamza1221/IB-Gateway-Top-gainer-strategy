import logging
import time
from datetime import datetime
from ib_insync import IB

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class IBConnectionManager:
    """
    Handles robust IB Gateway connection with automatic reconnection.
    Ensures connection is restored even after gateway shutdown/restart.
    """
    
    def __init__(self, host='127.0.0.1', port=4002, client_id=1, reconnect_interval=5, max_retries=10):
        self.host = host
        self.port = port
        self.client_id = client_id
        self.reconnect_interval = reconnect_interval
        self.max_retries = max_retries
        self.ib = IB()
        self.is_connected = False
        
    def connect(self):
        """Establish connection to IB Gateway with retry logic."""
        retries = 0
        while retries < self.max_retries:
            try:
                if not self.ib.isConnected():
                    logger.info(f"Attempting to connect to IB Gateway at {self.host}:{self.port}...")
                    self.ib.connect(self.host, self.port, clientId=self.client_id)
                    self.is_connected = True
                    logger.info("✓ Connected to IB Gateway successfully")
                    return True
                else:
                    self.is_connected = True
                    return True
            except Exception as e:
                retries += 1
                logger.warning(f"Connection failed (attempt {retries}/{self.max_retries}): {e}")
                if retries < self.max_retries:
                    logger.info(f"Retrying in {self.reconnect_interval} seconds...")
                    time.sleep(self.reconnect_interval)
        
        logger.error("Failed to connect after max retries")
        self.is_connected = False
        return False
    
    def ensure_connected(self):
        """Check connection and reconnect if necessary."""
        try:
            #print("Checking IB Gateway connection...", self.ib.isConnected())
            if not self.ib.isConnected():
                logger.warning("Connection lost, attempting to reconnect...")
                return self.connect()
            
            return True
        except Exception as e:
            logger.error(f"Error checking connection: {e}")
            return self.connect()
    
    def get_ib(self):
        """Return IB instance, ensuring it's connected."""
        self.ensure_connected()
        return self.ib
    
    def disconnect(self):
        """Gracefully disconnect from IB Gateway."""
        try:
            self.ib.disconnect()
            self.is_connected = False
            logger.info("Disconnected from IB Gateway")
        except Exception as e:
            logger.error(f"Error disconnecting: {e}")
