"""
HTTPS/TLS Configuration Module for NEXI Services
Handles SSL/TLS certificate generation and management
Supports both self-signed and Let's Encrypt certificates
"""

import ssl
import os
from pathlib import Path
from typing import Optional, Dict, Any
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


@dataclass
class SSLConfig:
    """SSL/TLS configuration"""
    enabled: bool = True
    cert_file: Optional[str] = None
    key_file: Optional[str] = None
    keyfile_password: Optional[str] = None
    ca_certs: Optional[str] = None
    verify_mode: str = "CERT_REQUIRED"
    protocols: str = "TLSv1_2,TLSv1_3"
    ciphers: Optional[str] = None


class SSLContextManager:
    """Manage SSL/TLS contexts for services"""
    
    def __init__(self, cert_dir: str = "config/certificates"):
        """
        Initialize SSL context manager
        
        Args:
            cert_dir: Directory for storing certificates
        """
        self.cert_dir = Path(cert_dir)
        self.cert_dir.mkdir(parents=True, exist_ok=True)
        self.contexts: Dict[str, ssl.SSLContext] = {}
    
    def create_ssl_context(
        self,
        service_name: str,
        cert_file: Optional[str] = None,
        key_file: Optional[str] = None,
        ca_file: Optional[str] = None,
        server_side: bool = True,
        verify_mode: str = "CERT_REQUIRED"
    ) -> ssl.SSLContext:
        """
        Create SSL context for a service.
        
        Args:
            service_name: Name of the service
            cert_file: Path to certificate file
            key_file: Path to private key file
            ca_file: Path to CA certificate file
            server_side: True for server, False for client
            verify_mode: Certificate verification mode
        
        Returns:
            ssl.SSLContext configured for the service
        """
        # Use TLSv1.2+ only (no SSLv3, TLSv1.0, TLSv1.1)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER if server_side else ssl.PROTOCOL_TLS_CLIENT)
        
        # Set secure options
        context.options |= ssl.OP_NO_TLSv1 | ssl.OP_NO_TLSv1_1
        context.options |= ssl.OP_CIPHER_SERVER_PREFERENCE
        
        # Load certificates if provided
        if cert_file and key_file:
            try:
                context.load_cert_chain(cert_file, keyfile=key_file)
                logger.info(f"SSL: Loaded certificate for {service_name} from {cert_file}")
            except ssl.SSLError as e:
                logger.error(f"SSL: Failed to load certificate for {service_name}: {e}")
                raise
        
        # Load CA certificates if provided
        if ca_file:
            try:
                context.load_verify_locations(ca_file)
                logger.info(f"SSL: Loaded CA certificates from {ca_file}")
            except ssl.SSLError as e:
                logger.error(f"SSL: Failed to load CA certificates: {e}")
                raise
        
        # Set verification mode
        if verify_mode == "CERT_REQUIRED":
            context.verify_mode = ssl.CERT_REQUIRED
            context.check_hostname = True
        elif verify_mode == "CERT_OPTIONAL":
            context.verify_mode = ssl.CERT_OPTIONAL
        else:
            context.verify_mode = ssl.CERT_NONE
            context.check_hostname = False
        
        self.contexts[service_name] = context
        return context
    
    def get_context(self, service_name: str) -> Optional[ssl.SSLContext]:
        """Get cached SSL context for a service"""
        return self.contexts.get(service_name)
    
    def generate_self_signed_cert(
        self,
        service_name: str,
        days: int = 365
    ) -> tuple[str, str]:
        """
        Generate self-signed certificate for development.
        
        Args:
            service_name: Name of the service
            days: Certificate validity in days
        
        Returns:
            Tuple of (cert_file, key_file) paths
        """
        cert_file = self.cert_dir / f"{service_name}.crt"
        key_file = self.cert_dir / f"{service_name}.key"
        
        # Check if certificates already exist
        if cert_file.exists() and key_file.exists():
            logger.info(f"SSL: Self-signed certificate already exists for {service_name}")
            return str(cert_file), str(key_file)
        
        # Generate self-signed certificate
        try:
            import subprocess
            command = [
                "openssl", "req", "-x509", "-newkey", "rsa:2048",
                "-keyout", str(key_file),
                "-out", str(cert_file),
                "-days", str(days),
                "-nodes",
                "-subj", f"/CN={service_name}"
            ]
            
            subprocess.run(command, check=True, capture_output=True)
            logger.info(f"SSL: Generated self-signed certificate for {service_name}")
            return str(cert_file), str(key_file)
        
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            logger.error(f"SSL: Failed to generate self-signed certificate: {e}")
            raise
    
    def validate_certificate(self, cert_file: str) -> Dict[str, Any]:
        """
        Validate a certificate file.
        
        Args:
            cert_file: Path to certificate file
        
        Returns:
            Dictionary with certificate details
        """
        try:
            import ssl
            cert_data = ssl.DER_cert_to_PEM_cert(
                open(cert_file, 'rb').read()
            )
            
            # Parse certificate info
            from cryptography import x509
            from cryptography.hazmat.backends import default_backend
            
            cert = x509.load_pem_x509_certificate(
                cert_data.encode(),
                default_backend()
            )
            
            return {
                "subject": cert.subject.rfc4514_string(),
                "issuer": cert.issuer.rfc4514_string(),
                "not_before": cert.not_valid_before,
                "not_after": cert.not_valid_after,
                "valid": cert.not_valid_before <= datetime.utcnow() <= cert.not_valid_after,
                "days_until_expiry": (cert.not_valid_after - datetime.utcnow()).days
            }
        except Exception as e:
            logger.error(f"SSL: Failed to validate certificate: {e}")
            return {"valid": False, "error": str(e)}


class HTTPSConfig:
    """HTTPS configuration for FastAPI services"""
    
    def __init__(self, ssl_config: SSLConfig, service_name: str = "default"):
        """
        Initialize HTTPS configuration
        
        Args:
            ssl_config: SSL configuration
            service_name: Name of the service
        """
        self.ssl_config = ssl_config
        self.service_name = service_name
        self.context_manager = SSLContextManager()
    
    @property
    def is_enabled(self) -> bool:
        """Check if HTTPS is enabled"""
        return self.ssl_config.enabled
    
    @property
    def ssl_context(self) -> Optional[ssl.SSLContext]:
        """Get SSL context for FastAPI"""
        if not self.is_enabled:
            return None
        
        if not self.ssl_config.cert_file or not self.ssl_config.key_file:
            return None
        
        try:
            return self.context_manager.create_ssl_context(
                self.service_name,
                cert_file=self.ssl_config.cert_file,
                key_file=self.ssl_config.key_file,
                ca_file=self.ssl_config.ca_certs,
                verify_mode=self.ssl_config.verify_mode
            )
        except ssl.SSLError as e:
            logger.error(f"Failed to create SSL context: {e}")
            return None
    
    @property
    def uvicorn_config(self) -> Dict[str, Any]:
        """Get Uvicorn configuration for HTTPS"""
        if not self.is_enabled:
            return {}
        
        return {
            "ssl_keyfile": self.ssl_config.key_file,
            "ssl_certfile": self.ssl_config.cert_file,
            "ssl_ca_certs": self.ssl_config.ca_certs,
            "ssl_version": ssl.PROTOCOL_TLS_SERVER,
            "ssl_cert_reqs": 0,  # ssl.VerifyMode.CERT_NONE
            "ssl_ciphers": self.ssl_config.ciphers
        }
    
    def get_uvicorn_kwargs(self) -> Dict[str, Any]:
        """Get all Uvicorn SSL/TLS kwargs"""
        kwargs = {}
        
        if self.ssl_config.enabled and self.ssl_config.cert_file and self.ssl_config.key_file:
            kwargs["ssl_keyfile"] = self.ssl_config.key_file
            kwargs["ssl_certfile"] = self.ssl_config.cert_file
            
            if self.ssl_config.ca_certs:
                kwargs["ssl_ca_certs"] = self.ssl_config.ca_certs
        
        return kwargs


# ============================================================================
# CERTIFICATE UTILITIES
# ============================================================================

def setup_development_certificates(services: list[str], cert_dir: str = "config/certificates") -> Dict[str, tuple[str, str]]:
    """
    Setup self-signed certificates for all services (development only).
    
    Args:
        services: List of service names
        cert_dir: Directory for storing certificates
    
    Returns:
        Dictionary mapping service names to (cert_file, key_file) tuples
    """
    manager = SSLContextManager(cert_dir)
    certs = {}
    
    for service in services:
        try:
            cert_file, key_file = manager.generate_self_signed_cert(service)
            certs[service] = (cert_file, key_file)
        except Exception as e:
            logger.error(f"Failed to setup certificate for {service}: {e}")
    
    return certs


def get_ssl_config(
    enabled: bool = True,
    cert_file: Optional[str] = None,
    key_file: Optional[str] = None,
    ca_certs: Optional[str] = None
) -> SSLConfig:
    """
    Create SSL configuration
    
    Args:
        enabled: Enable HTTPS
        cert_file: Path to certificate file
        key_file: Path to private key file
        ca_certs: Path to CA certificate file
    
    Returns:
        SSLConfig instance
    """
    return SSLConfig(
        enabled=enabled,
        cert_file=cert_file,
        key_file=key_file,
        ca_certs=ca_certs
    )
