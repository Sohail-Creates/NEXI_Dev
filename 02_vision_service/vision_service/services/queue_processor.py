"""
FEATURE #3: Vision Service Queue Processor

Background processor for queued face detection requests.
Automatically retries queued requests when Vision Service becomes available.

Author: Integration Team
"""

import logging
import time
import threading
from typing import Optional
import aiohttp
import asyncio


logger = logging.getLogger(__name__)


class VisionQueueProcessor:
    """
    Background processor for queued face detection requests.
    
    Features:
    - Automatic queue processing on background thread
    - Configurable polling interval
    - Graceful shutdown
    - Error handling with retry support
    """
    
    def __init__(
        self,
        queue_service,
        vision_service_url: str = "http://localhost:8001",
        poll_interval: float = 5.0,
        batch_size: int = 10
    ):
        """
        Initialize vision queue processor.
        
        Args:
            queue_service: VisionQueueService instance
            vision_service_url: URL of Vision Service
            poll_interval: Seconds between queue checks
            batch_size: Maximum requests to process per iteration
        """
        self.queue_service = queue_service
        self.vision_service_url = vision_service_url
        self.poll_interval = poll_interval
        self.batch_size = batch_size
        
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._http_session: Optional[aiohttp.ClientSession] = None
        
        logger.info(
            f"Vision queue processor initialized: poll_interval={poll_interval}s, "
            f"batch_size={batch_size}"
        )
    
    def start(self):
        """Start background processing thread."""
        with self._lock:
            if self._running:
                logger.warning("Vision queue processor already running")
                return
            
            self._running = True
            self._thread = threading.Thread(
                target=self._process_loop,
                name="VisionQueueProcessor",
                daemon=True
            )
            self._thread.start()
            
            logger.info("Vision queue processor started")
    
    def stop(self, timeout: float = 30.0):
        """
        Stop background processing thread.
        
        Args:
            timeout: Maximum seconds to wait for thread to finish
        """
        with self._lock:
            if not self._running:
                logger.warning("Vision queue processor not running")
                return
            
            self._running = False
        
        # Wait for thread to finish
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)
            
            if self._thread.is_alive():
                logger.warning(
                    f"Vision queue processor thread did not stop within {timeout}s"
                )
            else:
                logger.info("Vision queue processor stopped")
    
    def is_running(self) -> bool:
        """Check if processor is running."""
        return self._running
    
    def _process_loop(self):
        """Main processing loop (runs in background thread)."""
        logger.info("Vision queue processor loop started")
        
        consecutive_errors = 0
        max_consecutive_errors = 5
        
        while self._running:
            try:
                # Check if Vision Service is available
                if not self._check_vision_service_health():
                    logger.debug("Vision Service not available, skipping queue processing")
                    time.sleep(self.poll_interval)
                    continue
                
                # Process batch of requests
                processed = self._process_batch()
                
                if processed > 0:
                    logger.info(f"Processed {processed} queued vision requests")
                    consecutive_errors = 0  # Reset error counter on success
                
                # Sleep before next iteration
                time.sleep(self.poll_interval)
                
            except Exception as e:
                consecutive_errors += 1
                logger.error(
                    f"Error in vision queue processor loop (attempt {consecutive_errors}/"
                    f"{max_consecutive_errors}): {e}",
                    exc_info=True
                )
                
                # If too many consecutive errors, back off
                if consecutive_errors >= max_consecutive_errors:
                    logger.critical(
                        f"Too many consecutive errors ({consecutive_errors}), "
                        "increasing backoff time"
                    )
                    time.sleep(self.poll_interval * 5)
                    consecutive_errors = 0
                else:
                    time.sleep(self.poll_interval)
        
        logger.info("Vision queue processor loop stopped")
    
    def _check_vision_service_health(self) -> bool:
        """
        Check if Vision Service is healthy and available.
        
        Returns:
            bool: True if service is available, False otherwise
        """
        try:
            import requests
            response = requests.get(
                f"{self.vision_service_url}/health",
                timeout=5
            )
            is_healthy = response.status_code == 200
            if is_healthy:
                logger.debug("Vision Service is healthy")
            else:
                logger.warning(f"Vision Service returned status {response.status_code}")
            return is_healthy
        except Exception as e:
            logger.warning(f"Failed to check Vision Service health: {e}")
            return False
    
    def _process_batch(self) -> int:
        """
        Process a batch of queued vision requests.
        
        Returns:
            int: Number of requests processed
        """
        processed_count = 0
        
        for _ in range(self.batch_size):
            if not self._running:
                break
            
            # Get next request from queue
            request = self.queue_service.dequeue_request()
            if request is None:
                break  # No more requests
            
            request_id = request['id']
            request_type = request['request_type']
            request_data = request['request_data']
            image_file_path = request['image_file_path']
            
            try:
                # Mark as processing
                self.queue_service.mark_request_processing(request_id)
                
                # Send to Vision Service
                result = self._send_request_to_vision_service(
                    request_type,
                    request_data,
                    image_file_path
                )
                
                # Mark as success
                self.queue_service.mark_request_success(request_id)
                processed_count += 1
                
                logger.debug(
                    f"Vision request {request_id} processed successfully: "
                    f"type={request_type}"
                )
                
            except Exception as e:
                # Network/API error - mark for retry
                error_message = str(e)
                self.queue_service.mark_request_failed(request_id, error_message)
                
                logger.warning(
                    f"Failed to process vision request {request_id}: {error_message}"
                )
                
                # Stop processing batch if Vision Service is having issues
                break
        
        return processed_count
    
    def _send_request_to_vision_service(
        self,
        request_type: str,
        request_data: dict,
        image_file_path: Optional[str] = None
    ) -> dict:
        """
        Send queued request to Vision Service.
        
        Args:
            request_type: Type of request
            request_data: Request payload
            image_file_path: Path to image file
        
        Returns:
            dict: Vision Service response
        
        Raises:
            Exception: If request fails
        """
        try:
            if request_type == 'face_detection' and image_file_path:
                # Send face detection request with image
                import requests
                
                with open(image_file_path, 'rb') as f:
                    files = {'file': f}
                    response = requests.post(
                        f"{self.vision_service_url}/detect/faces/upload",
                        files=files,
                        timeout=30
                    )
                
                if response.status_code != 200:
                    raise Exception(f"Vision Service returned {response.status_code}: {response.text}")
                
                return response.json()
            
            else:
                raise Exception(f"Unknown request type: {request_type}")
        
        except Exception as e:
            logger.error(f"Error sending request to Vision Service: {e}")
            raise
    
    def process_now(self) -> int:
        """
        Manually trigger immediate queue processing.
        
        Returns:
            int: Number of requests processed
        """
        logger.info("Manual vision queue processing triggered")
        
        try:
            if not self._check_vision_service_health():
                logger.warning("Vision Service not available for manual processing")
                return 0
            
            processed = self._process_batch()
            logger.info(f"Manual processing completed: {processed} requests")
            
            return processed
            
        except Exception as e:
            logger.error(f"Error in manual vision queue processing: {e}", exc_info=True)
            return 0
    
    def get_status(self) -> dict:
        """
        Get processor status.
        
        Returns:
            dict: Status information
        """
        try:
            queue_stats = self.queue_service.get_queue_stats()
        except Exception:
            queue_stats = {"error": "Cannot get queue stats"}
        
        return {
            'running': self._running,
            'poll_interval': self.poll_interval,
            'batch_size': self.batch_size,
            'queue_stats': queue_stats
        }
