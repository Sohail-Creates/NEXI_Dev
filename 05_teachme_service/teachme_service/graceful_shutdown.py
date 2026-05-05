"""
Graceful Shutdown Manager
Handles cleanup, resource management, and state persistence on service shutdown
"""

import asyncio
import logging
import signal
import sys
from typing import Callable, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class GracefulShutdownManager:
    """
    Manages graceful shutdown of services.
    Ensures all resources are properly cleaned up and state is persisted.
    """
    
    def __init__(self):
        self.shutdown_handlers: List[Callable] = []
        self.is_shutting_down = False
        self.shutdown_start_time: Optional[datetime] = None
        self.shutdown_timeout = 30  # seconds
        
        logger.info("GracefulShutdownManager initialized")
    
    def register_shutdown_handler(self, handler: Callable) -> None:
        """
        Register a callback to be called on shutdown.
        
        Handler should be either:
        - Sync function: handler()
        - Async function: async handler()
        
        Args:
            handler: Callable to execute on shutdown
        """
        self.shutdown_handlers.append(handler)
        logger.debug(f"Registered shutdown handler: {handler.__name__}")
    
    async def shutdown(self, signal_name: str = "SIGTERM") -> None:
        """
        Execute graceful shutdown sequence.
        
        Args:
            signal_name: Signal that triggered shutdown
        """
        if self.is_shutting_down:
            logger.warning("Shutdown already initiated, ignoring")
            return
        
        self.is_shutting_down = True
        self.shutdown_start_time = datetime.utcnow()
        logger.info(f"Graceful shutdown initiated (signal: {signal_name})")
        
        # Execute all shutdown handlers
        failed_handlers = []
        
        for handler in self.shutdown_handlers:
            try:
                logger.debug(f"Executing shutdown handler: {handler.__name__}")
                
                # Check if handler is async
                if asyncio.iscoroutinefunction(handler):
                    await asyncio.wait_for(handler(), timeout=self.shutdown_timeout)
                else:
                    handler()
                
                logger.debug(f" Shutdown handler completed: {handler.__name__}")
                
            except asyncio.TimeoutError:
                logger.error(f" Shutdown handler timeout: {handler.__name__}")
                failed_handlers.append(handler.__name__)
                
            except Exception as e:
                logger.error(f" Shutdown handler error ({handler.__name__}): {e}")
                failed_handlers.append(handler.__name__)
        
        elapsed = (datetime.utcnow() - self.shutdown_start_time).total_seconds()
        
        if failed_handlers:
            logger.warning(f"Shutdown completed with {len(failed_handlers)} handler failures:")
            for name in failed_handlers:
                logger.warning(f"  - {name}")
        
        logger.info(f"Graceful shutdown completed in {elapsed:.2f}s")
    
    def register_signal_handlers(self, loop: Optional[asyncio.AbstractEventLoop] = None) -> None:
        """
        Register system signal handlers for graceful shutdown.
        
        Handles SIGTERM (normal termination) and SIGINT (Ctrl+C)
        
        Args:
            loop: Event loop (auto-detected if not provided)
        """
        if loop is None:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                logger.warning("Could not get event loop for signal handlers")
                return
        
        def signal_handler(signum, frame):
            signal_name = signal.Signals(signum).name if hasattr(signal, 'Signals') else str(signum)
            logger.info(f"Received signal {signal_name}, initiating graceful shutdown")
            
            # Schedule shutdown in event loop
            asyncio.create_task(self.shutdown(signal_name))
        
        # Register handlers for SIGTERM and SIGINT
        for sig in [signal.SIGTERM, signal.SIGINT]:
            loop.add_signal_handler(sig, lambda s=sig: signal_handler(s, None))
            logger.debug(f"Registered signal handler for {signal.Signals(sig).name if hasattr(signal, 'Signals') else str(sig)}")


# Global shutdown manager
_shutdown_manager: Optional[GracefulShutdownManager] = None


def get_shutdown_manager() -> GracefulShutdownManager:
    """Get or create global shutdown manager"""
    global _shutdown_manager
    if _shutdown_manager is None:
        _shutdown_manager = GracefulShutdownManager()
    return _shutdown_manager


def init_graceful_shutdown() -> GracefulShutdownManager:
    """Initialize graceful shutdown system"""
    manager = get_shutdown_manager()
    logger.info("Graceful shutdown system initialized")
    return manager
