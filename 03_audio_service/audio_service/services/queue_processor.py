"""
Queue Processor Service.

This service runs a background thread to process queued commands when the
backend becomes available. It periodically checks for pending commands and
attempts to send them to the backend.

Author: Integration Team
"""

import logging
import time
import threading
from typing import Optional

from .queue_service import QueueService
from .backend_service import BackendService
from ..utils.errors import NetworkError, APIError


logger = logging.getLogger(__name__)


class QueueProcessor:
    """
    Background processor for queued commands.
    
    Features:
    - Automatic queue processing when backend is available
    - Configurable polling interval
    - Graceful shutdown
    - Error handling with retry support
    """
    
    def __init__(
        self,
        queue_service: QueueService,
        backend_service: BackendService,
        poll_interval: float = 10.0,
        batch_size: int = 10
    ):
        """
        Initialize queue processor.
        
        Args:
            queue_service: Queue service instance
            backend_service: Backend service instance
            poll_interval: Seconds between queue checks
            batch_size: Maximum commands to process per iteration
        """
        self.queue_service = queue_service
        self.backend_service = backend_service
        self.poll_interval = poll_interval
        self.batch_size = batch_size
        
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        
        logger.info(
            f"Queue processor initialized: poll_interval={poll_interval}s, "
            f"batch_size={batch_size}"
        )
    
    def start(self):
        """Start background processing thread."""
        with self._lock:
            if self._running:
                logger.warning("Queue processor already running")
                return
            
            self._running = True
            self._thread = threading.Thread(
                target=self._process_loop,
                name="QueueProcessor",
                daemon=True
            )
            self._thread.start()
            
            logger.info("Queue processor started")
    
    def stop(self, timeout: float = 30.0):
        """
        Stop background processing thread.
        
        Args:
            timeout: Maximum seconds to wait for thread to finish
        """
        with self._lock:
            if not self._running:
                logger.warning("Queue processor not running")
                return
            
            self._running = False
        
        # Wait for thread to finish
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)
            
            if self._thread.is_alive():
                logger.warning(
                    f"Queue processor thread did not stop within {timeout}s"
                )
            else:
                logger.info("Queue processor stopped")
    
    def is_running(self) -> bool:
        """Check if processor is running."""
        return self._running
    
    def _process_loop(self):
        """Main processing loop (runs in background thread)."""
        logger.info("Queue processor loop started")
        
        consecutive_errors = 0
        max_consecutive_errors = 5
        
        while self._running:
            try:
                # Check if backend is available
                if not self.backend_service.check_health():
                    logger.debug("Backend not available, skipping queue processing")
                    time.sleep(self.poll_interval)
                    continue
                
                # Process batch of commands
                processed = self._process_batch()
                
                if processed > 0:
                    logger.info(f"Processed {processed} queued commands")
                    consecutive_errors = 0  # Reset error counter on success
                
                # Sleep before next iteration
                time.sleep(self.poll_interval)
                
            except Exception as e:
                consecutive_errors += 1
                logger.error(
                    f"Error in queue processor loop (attempt {consecutive_errors}/"
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
        
        logger.info("Queue processor loop stopped")
    
    def _process_batch(self) -> int:
        """
        Process a batch of queued commands.
        
        Returns:
            int: Number of commands processed
        """
        processed_count = 0
        
        for _ in range(self.batch_size):
            if not self._running:
                break
            
            # Get next command from queue
            command = self.queue_service.dequeue_command()
            if command is None:
                break  # No more commands
            
            command_id = command['id']
            command_type = command['command_type']
            command_data = command['command_data']
            
            try:
                # Mark as processing
                self.queue_service.mark_command_processing(command_id)
                
                # Send to backend
                result = self._send_command_to_backend(
                    command_type,
                    command_data
                )
                
                # Mark as success
                self.queue_service.mark_command_success(command_id)
                processed_count += 1
                
                logger.debug(
                    f"Command {command_id} processed successfully: "
                    f"type={command_type}"
                )
                
            except (NetworkError, APIError) as e:
                # Network/API error - mark for retry
                error_message = str(e)
                self.queue_service.mark_command_failed(command_id, error_message)
                
                logger.warning(
                    f"Failed to process command {command_id}: {error_message}"
                )
                
                # Stop processing batch if backend is having issues
                break
                
            except Exception as e:
                # Unexpected error - mark as failed
                error_message = f"Unexpected error: {e}"
                self.queue_service.mark_command_failed(command_id, error_message)
                
                logger.error(
                    f"Unexpected error processing command {command_id}: {e}",
                    exc_info=True
                )
        
        return processed_count
    
    def _send_command_to_backend(
        self,
        command_type: str,
        command_data: dict
    ) -> dict:
        """
        Send command to backend based on type.
        
        Args:
            command_type: Type of command
            command_data: Command payload
        
        Returns:
            dict: Backend response
        """
        # Route to appropriate backend method based on command type
        if command_type == 'transcription':
            return self.backend_service.send_transcription(
                text=command_data.get('text', ''),
                language=command_data.get('language', 'en'),
                confidence=command_data.get('confidence', 0.0),
                metadata=command_data.get('metadata')
            )
        
        elif command_type == 'speaker_verification':
            return self.backend_service.send_speaker_verification(
                speaker_id=command_data.get('speaker_id', ''),
                is_verified=command_data.get('is_verified', False),
                confidence=command_data.get('confidence', 0.0),
                metadata=command_data.get('metadata')
            )
        
        elif command_type == 'pipeline_result':
            return self.backend_service.send_pipeline_result(
                transcription=command_data.get('transcription', ''),
                speaker_id=command_data.get('speaker_id'),
                is_speaker_verified=command_data.get('is_speaker_verified', False),
                metadata=command_data.get('metadata')
            )
        
        else:
            # Generic command send
            return self.backend_service.send_command(
                command_type=command_type,
                command_data=command_data
            )
    
    def process_now(self) -> int:
        """
        Manually trigger immediate queue processing.
        
        Returns:
            int: Number of commands processed
        """
        logger.info("Manual queue processing triggered")
        
        try:
            if not self.backend_service.check_health():
                logger.warning("Backend not available for manual processing")
                return 0
            
            processed = self._process_batch()
            logger.info(f"Manual processing completed: {processed} commands")
            
            return processed
            
        except Exception as e:
            logger.error(f"Error in manual queue processing: {e}", exc_info=True)
            return 0
    
    def get_status(self) -> dict:
        """
        Get processor status (lightweight, non-blocking).
        
        Returns:
            dict: Status information without blocking backend checks
        """
        try:
            queue_stats = self.queue_service.get_queue_stats()
        except Exception:
            queue_stats = {"error": "Cannot get queue stats"}
        
        return {
            'running': self._running,
            'poll_interval': self.poll_interval,
            'batch_size': self.batch_size,
            'queue_stats': queue_stats,
            'circuit_breaker_state': self.backend_service.get_circuit_breaker_state()
        }
