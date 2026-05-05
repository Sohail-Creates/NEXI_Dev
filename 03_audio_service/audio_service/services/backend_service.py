"""
Backend Communication Service.

This service handles all communication with the central backend server using
circuit breaker pattern for resilience and retry logic for reliability.

Author: Integration Team
"""

import logging
import time
from typing import Optional, Dict, Any
from urllib.parse import urljoin
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

import sys
from pathlib import Path

# Add parent directories to path for shared utilities
sys_path = str(Path(__file__).resolve().parent.parent.parent.parent)
if sys_path not in sys.path:
    sys.path.insert(0, sys_path)

from shared.utils.circuit_breaker import CircuitBreaker
from ..utils.errors import (
    NetworkError,
    APIError,
    APITimeoutError,
    BackendConnectionError
)


logger = logging.getLogger(__name__)


class BackendService:
    """
    Manages communication with central backend server.
    
    Features:
    - Circuit breaker pattern for resilience
    - Automatic retry with exponential backoff
    - Connection pooling
    - HTTPS with SSL verification
    - Timeout management
    """
    
    def __init__(
        self,
        base_url: str,
        api_key: Optional[str] = None,
        timeout: float = 30.0,
        max_retries: int = 3,
        verify_ssl: bool = True,
        circuit_breaker_config: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize backend service.
        
        Args:
            base_url: Base URL of backend API
            api_key: Optional API key for authentication
            timeout: Request timeout in seconds
            max_retries: Maximum retry attempts
            verify_ssl: Whether to verify SSL certificates
            circuit_breaker_config: Circuit breaker configuration
        """
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.timeout = timeout
        self.max_retries = max_retries
        self.verify_ssl = verify_ssl
        
        # Initialize circuit breaker
        cb_config = circuit_breaker_config or {}
        self.circuit_breaker = CircuitBreaker(
            name="BackendService",
            failure_threshold=cb_config.get('failure_threshold', 5),
            recovery_timeout=cb_config.get('recovery_timeout', 60.0),
            success_threshold=cb_config.get('half_open_attempts', 3)
        )
        
        # Configure session with retry strategy
        self.session = self._create_session()
        
        logger.info(
            f"Backend service initialized: url={base_url}, "
            f"timeout={timeout}s, max_retries={max_retries}"
        )
    
    def _create_session(self) -> requests.Session:
        """
        Create requests session with retry strategy and connection pooling.
        
        Returns:
            requests.Session: Configured session
        """
        session = requests.Session()
        
        # Configure retry strategy
        retry_strategy = Retry(
            total=self.max_retries,
            backoff_factor=1,  # Exponential backoff: 0s, 1s, 2s, 4s
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "POST", "PUT", "DELETE", "OPTIONS", "TRACE"]
        )
        
        # Mount adapter with retry strategy
        adapter = HTTPAdapter(
            max_retries=retry_strategy,
            pool_connections=10,
            pool_maxsize=20
        )
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        
        # Set default headers
        session.headers.update({
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'User-Agent': 'NEXI-Audio-Service/1.0'
        })
        
        # Add API key if provided
        if self.api_key:
            session.headers.update({
                'Authorization': f'Bearer {self.api_key}'
            })
        
        return session
    
    def _build_url(self, endpoint: str) -> str:
        """
        Build full URL from endpoint.
        
        Args:
            endpoint: API endpoint path
        
        Returns:
            str: Full URL
        """
        # Ensure endpoint starts with /
        if not endpoint.startswith('/'):
            endpoint = f'/{endpoint}'
        
        return urljoin(self.base_url, endpoint)
    
    def _handle_response(self, response: requests.Response) -> Dict[str, Any]:
        """
        Handle HTTP response and extract data.
        
        Args:
            response: HTTP response object
        
        Returns:
            Dict: Response data
        
        Raises:
            APIError: If response indicates error
        """
        try:
            # Check for HTTP errors
            response.raise_for_status()
            
            # Parse JSON response
            data = response.json()
            
            return data
            
        except requests.exceptions.HTTPError as e:
            status_code = response.status_code
            
            try:
                error_data = response.json()
                error_message = error_data.get('detail', str(e))
            except Exception:
                error_message = str(e)
            
            logger.error(
                f"HTTP error {status_code}: {error_message}"
            )
            
            raise APIError(
                f"Backend API error ({status_code}): {error_message}",
                status_code=status_code
            )
        
        except ValueError as e:
            logger.error(f"Invalid JSON response: {e}")
            raise APIError(f"Invalid JSON response: {e}")
    
    def check_health(self) -> bool:
        """
        Check if backend service is reachable.
        
        Returns:
            bool: True if backend is healthy
        """
        try:
            url = self._build_url('/health')
            
            response = self.session.get(
                url,
                timeout=5.0,  # Short timeout for health check
                verify=self.verify_ssl
            )
            
            return response.status_code == 200
            
        except Exception as e:
            logger.warning(f"Backend health check failed: {e}")
            return False
    
    def send_command(
        self,
        command_type: str,
        command_data: Dict[str, Any],
        endpoint: str = '/api/v1/commands'
    ) -> Dict[str, Any]:
        """
        Send command to backend.
        
        Args:
            command_type: Type of command
            command_data: Command payload
            endpoint: API endpoint (default: /api/v1/commands)
        
        Returns:
            Dict: Backend response
        
        Raises:
            NetworkError: If network operation fails
            APIError: If backend returns error
            APITimeoutError: If request times out
        """
        try:
            # Use circuit breaker to protect against cascading failures
            return self.circuit_breaker.call(
                self._send_command_internal,
                command_type,
                command_data,
                endpoint
            )
            
        except Exception as e:
            if isinstance(e, (NetworkError, APIError, APITimeoutError)):
                raise
            
            logger.error(f"Unexpected error sending command: {e}")
            raise NetworkError(f"Failed to send command: {e}")
    
    def _send_command_internal(
        self,
        command_type: str,
        command_data: Dict[str, Any],
        endpoint: str
    ) -> Dict[str, Any]:
        """Internal method for sending command (used by circuit breaker)."""
        try:
            url = self._build_url(endpoint)
            
            payload = {
                'command_type': command_type,
                'data': command_data,
                'timestamp': time.time()
            }
            
            logger.info(f"Sending command to backend: type={command_type}, url={url}")
            
            response = self.session.post(
                url,
                json=payload,
                timeout=self.timeout,
                verify=self.verify_ssl
            )
            
            result = self._handle_response(response)
            
            logger.info(f"Command sent successfully: type={command_type}")
            
            return result
            
        except requests.exceptions.Timeout as e:
            logger.error(f"Request timeout after {self.timeout}s: {e}")
            raise APITimeoutError(f"Backend request timeout: {e}")
        
        except requests.exceptions.ConnectionError as e:
            logger.error(f"Connection error: {e}")
            raise BackendConnectionError(f"Cannot connect to backend: {e}")
        
        except requests.exceptions.RequestException as e:
            logger.error(f"Request failed: {e}")
            raise NetworkError(f"Backend request failed: {e}")
    
    def send_transcription(
        self,
        text: str,
        language: str,
        confidence: float,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Send transcription result to backend.
        
        Args:
            text: Transcribed text
            language: Detected language code
            confidence: Transcription confidence score
            metadata: Optional additional metadata
        
        Returns:
            Dict: Backend response
        """
        command_data = {
            'text': text,
            'language': language,
            'confidence': confidence,
            'metadata': metadata or {}
        }
        
        return self.send_command(
            command_type='transcription',
            command_data=command_data,
            endpoint='/api/v1/transcriptions'
        )
    
    def send_speaker_verification(
        self,
        speaker_id: str,
        is_verified: bool,
        confidence: float,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Send speaker verification result to backend.
        
        Args:
            speaker_id: Speaker identifier
            is_verified: Whether speaker was verified
            confidence: Verification confidence score
            metadata: Optional additional metadata
        
        Returns:
            Dict: Backend response
        """
        command_data = {
            'speaker_id': speaker_id,
            'is_verified': is_verified,
            'confidence': confidence,
            'metadata': metadata or {}
        }
        
        return self.send_command(
            command_type='speaker_verification',
            command_data=command_data,
            endpoint='/api/v1/speaker-verifications'
        )
    
    def send_pipeline_result(
        self,
        transcription: str,
        speaker_id: Optional[str],
        is_speaker_verified: bool,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Send complete pipeline result to backend.
        
        Args:
            transcription: Transcribed text
            speaker_id: Speaker identifier
            is_speaker_verified: Whether speaker was verified
            metadata: Optional additional metadata
        
        Returns:
            Dict: Backend response
        """
        command_data = {
            'transcription': transcription,
            'speaker_id': speaker_id,
            'is_speaker_verified': is_speaker_verified,
            'metadata': metadata or {}
        }
        
        return self.send_command(
            command_type='pipeline_result',
            command_data=command_data,
            endpoint='/api/v1/pipeline-results'
        )
    
    def get_circuit_breaker_state(self) -> str:
        """
        Get current circuit breaker state.
        
        Returns:
            str: Circuit breaker state (CLOSED, OPEN, HALF_OPEN)
        """
        return self.circuit_breaker.state
    
    def reset_circuit_breaker(self):
        """Manually reset circuit breaker."""
        self.circuit_breaker.reset()
        logger.info("Circuit breaker manually reset")
    
    def close(self):
        """Close session and release resources."""
        try:
            self.session.close()
            logger.info("Backend service closed")
        except Exception as e:
            logger.error(f"Error closing backend service: {e}")
