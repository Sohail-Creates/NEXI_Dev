"""
CPU Utilization Monitor and Power Mode Manager.

Continuously monitors CPU usage and automatically adjusts power modes
to balance performance and energy consumption.

Features:
- Real-time CPU monitoring
- Automatic power mode switching based on CPU load
- Callback notification on mode changes
- Statistics tracking
- Graceful shutdown
"""

import asyncio
import psutil
import time
import logging
from typing import Optional, Callable, Dict
from datetime import datetime

logger = logging.getLogger(__name__)


class CPUMonitor:
    """Monitor CPU utilization and manage power modes."""
    
    # CPU threshold ranges
    CPU_THRESHOLDS = {
        "low_power": 80,      # If CPU > 80%, switch to low_power
        "balanced": 50,       # If CPU > 50%, switch to balanced
        "high_performance": 0  # Default
    }
    
    def __init__(self, check_interval: float = 5.0):
        """
        Initialize CPU monitor.
        
        Args:
            check_interval: Seconds between CPU checks (default 5.0)
        """
        self.check_interval = check_interval
        self.running = False
        self.monitor_task: Optional[asyncio.Task] = None
        self.current_mode = "high_performance"
        self.mode_callback: Optional[Callable] = None
        
        # History for averaging
        self.cpu_history = []
        self.max_history = 12  # Keep ~60 seconds of data (5s * 12)
        
        # Statistics
        self.stats = {
            "start_time": None,
            "samples_collected": 0,
            "mode_switches": 0,
            "current_mode": self.current_mode,
            "average_cpu": 0.0,
            "peak_cpu": 0.0,
            "min_cpu": 100.0
        }
        
        logger.info(f"CPUMonitor initialized (check_interval={check_interval}s)")
    
    def start(self, mode_callback: Optional[Callable] = None):
        """
        Start CPU monitoring.
        
        Args:
            mode_callback: Function to call when mode changes: callback(new_mode)
        """
        if self.running:
            logger.warning("CPU monitor already running")
            return
        
        self.running = True
        self.mode_callback = mode_callback
        self.stats["start_time"] = datetime.utcnow()
        
        # Create and start monitor task
        self.monitor_task = asyncio.create_task(self._monitor_loop())
        
        logger.info("CPU monitor started")
    
    async def _monitor_loop(self):
        """Background CPU monitoring loop."""
        try:
            while self.running:
                try:
                    # Get current CPU usage (non-blocking call)
                    cpu_percent = psutil.cpu_percent(interval=0.1)
                    
                    # Add to history
                    self.cpu_history.append(cpu_percent)
                    if len(self.cpu_history) > self.max_history:
                        self.cpu_history.pop(0)
                    
                    # Update statistics
                    self.stats["samples_collected"] += 1
                    self.stats["average_cpu"] = sum(self.cpu_history) / len(self.cpu_history)
                    self.stats["peak_cpu"] = max(self.stats["peak_cpu"], cpu_percent)
                    self.stats["min_cpu"] = min(self.stats["min_cpu"], cpu_percent)
                    
                    # Determine optimal power mode based on average CPU
                    new_mode = self._determine_mode(self.stats["average_cpu"])
                    
                    # If mode changed, notify callback
                    if new_mode != self.current_mode:
                        logger.info(
                            f"CPU mode change: {self.current_mode} → {new_mode} "
                            f"(CPU: {self.stats['average_cpu']:.1f}%, "
                            f"Current: {cpu_percent:.1f}%)"
                        )
                        self.current_mode = new_mode
                        self.stats["current_mode"] = new_mode
                        self.stats["mode_switches"] += 1
                        
                        if self.mode_callback:
                            try:
                                if asyncio.iscoroutinefunction(self.mode_callback):
                                    await self.mode_callback(new_mode)
                                else:
                                    self.mode_callback(new_mode)
                            except Exception as e:
                                logger.error(f"Error in mode callback: {e}")
                    
                    # Wait before next check
                    await asyncio.sleep(self.check_interval)
                    
                except asyncio.CancelledError:
                    logger.info("CPU monitor cancelled")
                    break
                except Exception as e:
                    logger.error(f"Error in CPU monitoring: {e}")
                    await asyncio.sleep(1)  # Brief wait before retry
                    
        except Exception as e:
            logger.error(f"Fatal error in CPU monitor: {e}")
        finally:
            self.running = False
            logger.info("CPU monitor stopped")
    
    def _determine_mode(self, cpu_percent: float) -> str:
        """
        Determine optimal power mode based on CPU usage.
        
        Args:
            cpu_percent: Average CPU usage percentage
        
        Returns:
            Power mode: "high_performance", "balanced", or "low_power"
        """
        if cpu_percent > self.CPU_THRESHOLDS["low_power"]:
            return "low_power"
        elif cpu_percent > self.CPU_THRESHOLDS["balanced"]:
            return "balanced"
        else:
            return "high_performance"
    
    def stop(self):
        """Stop CPU monitoring."""
        if not self.running:
            logger.warning("CPU monitor not running")
            return
        
        self.running = False
        
        if self.monitor_task:
            self.monitor_task.cancel()
        
        logger.info(
            f"CPU monitor stopped. "
            f"Samples: {self.stats['samples_collected']}, "
            f"Mode switches: {self.stats['mode_switches']}, "
            f"Average CPU: {self.stats['average_cpu']:.1f}%"
        )
    
    def get_stats(self) -> Dict:
        """
        Get current CPU statistics.
        
        Returns:
            Dict with CPU stats and mode information
        """
        uptime = None
        if self.stats["start_time"]:
            uptime = (datetime.utcnow() - self.stats["start_time"]).total_seconds()
        
        return {
            "current_cpu": self.cpu_history[-1] if self.cpu_history else 0,
            "average_cpu": self.stats["average_cpu"],
            "peak_cpu": self.stats["peak_cpu"],
            "min_cpu": self.stats["min_cpu"],
            "current_mode": self.stats["current_mode"],
            "mode_switches": self.stats["mode_switches"],
            "samples_collected": self.stats["samples_collected"],
            "uptime_seconds": uptime,
            "is_running": self.running
        }
    
    def get_current_mode(self) -> str:
        """Get current power mode."""
        return self.current_mode
    
    def __del__(self):
        """Cleanup on deletion."""
        if self.running:
            self.stop()
