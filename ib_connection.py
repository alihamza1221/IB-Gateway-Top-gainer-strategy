import logging
from ib_insync import IB, util
import config
import asyncio

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class IBConnectionManager:
    """
    Asyncio-based IB Connection Manager.
    Handles connection, reconnection, and provides IB instance.
    """
    
    def __init__(self):
        self.ib = IB()
        self.connected = False
        
    async def connect_async(self):
        """Establish async connection to IB Gateway."""
        max_retries = config.MAX_RETRIES
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                logger.info(f"[IB] Attempting to connect to IB Gateway at {config.IB_HOST}:{config.IB_PORT}...")
                await self.ib.connectAsync(
                    host=config.IB_HOST,
                    port=config.IB_PORT,
                    clientId=config.IB_CLIENT_ID
                )
                self.connected = True
                logger.info("[IB] ✓ Successfully connected to IB Gateway")
                return True
                
            except Exception as e:
                retry_count += 1
                logger.error(f"[IB] Connection failed (attempt {retry_count}/{max_retries}): {e}")
                
                if retry_count < max_retries:
                    logger.info(f"[IB] Retrying in {config.RECONNECT_INTERVAL} seconds...")
                    await asyncio.sleep(config.RECONNECT_INTERVAL)
                else:
                    logger.error("[IB] Max retries reached. Connection failed.")
                    self.connected = False
                    return False
    
    async def ensure_connected_async(self):
        """Check connection and reconnect if needed."""
        if not self.ib.isConnected():
            logger.warning("[IB] Connection lost. Attempting to reconnect...")
            self.connected = False
            return await self.connect_async()
        return True
    
    def get_ib(self):
        """Get the IB instance."""
        return self.ib
    
    def is_connected(self):
        """Check if connected."""
        return self.connected and self.ib.isConnected()
    
    async def disconnect_async(self):
        """Disconnect from IB Gateway."""
        if self.ib.isConnected():
            logger.info("[IB] Disconnecting from IB Gateway...")
            self.ib.disconnect()
            self.connected = False
            logger.info("[IB] Disconnected successfully")
