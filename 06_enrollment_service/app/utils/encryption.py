"""
Encryption utilities for secure data storage
"""
import os
from pathlib import Path
from typing import Optional, List

from cryptography.fernet import Fernet, InvalidToken
from pathlib import Path
from typing import Optional


class EncryptionManager:
    """Handles encryption and decryption of sensitive data"""
    
    def __init__(self, key_file: str = "./encryption.key", fallback_key_files: Optional[List[str]] = None) -> None:
        self.key_file: str = key_file
        self.fallback_key_files: List[str] = fallback_key_files or []
        self._cipher = None
        self._fallback_ciphers: List[Fernet] = []
        self._initialize_encryption()
    
    def _initialize_encryption(self) -> None:
        """Initialize encryption key"""
        if os.path.exists(self.key_file):
            # Load existing key
            with open(self.key_file, 'rb') as f:
                key: bytes = f.read()
        else:
            # Generate new key
            key: bytes = Fernet.generate_key()
            
            # Save key securely
            os.makedirs(os.path.dirname(self.key_file) or '.', exist_ok=True)
            with open(self.key_file, 'wb') as f:
                f.write(key)
            
            # Set restrictive permissions (Windows compatible)
            try:
                os.chmod(self.key_file, 0o600)
            except:
                pass  # Windows may not support chmod
        
        self._cipher = Fernet(key)

        for key_file in self.fallback_key_files:
            if not key_file or key_file == self.key_file:
                continue
            if not os.path.exists(key_file):
                continue
            try:
                with open(key_file, 'rb') as f:
                    fallback_key: bytes = f.read()
                self._fallback_ciphers.append(Fernet(fallback_key))
            except Exception:
                continue
    
    def encrypt(self, data: str) -> bytes:
        """
        Encrypt string data
        
        Args:
            data: String to encrypt
            
        Returns:
            Encrypted bytes
        """
        if not data:
            return b''
        
        return self._cipher.encrypt(data.encode())
    
    def decrypt(self, encrypted_data: bytes) -> str:
        """
        Decrypt encrypted data
        
        Args:
            encrypted_data: Encrypted bytes
            
        Returns:
            Decrypted string
        """
        if not encrypted_data:
            return ''
        
        try:
            return self._cipher.decrypt(encrypted_data).decode()
        except InvalidToken:
            for cipher in self._fallback_ciphers:
                try:
                    return cipher.decrypt(encrypted_data).decode()
                except InvalidToken:
                    continue
            raise
    
    def encrypt_file(self, file_path: str) -> str:
        """
        Encrypt a file in place
        
        Args:
            file_path: Path to file to encrypt
            
        Returns:
            Path to encrypted file (same as input)
        """
        with open(file_path, 'rb') as f:
            data: bytes = f.read()
        
        encrypted_data: bytes = self._cipher.encrypt(data)
        
        with open(file_path, 'wb') as f:
            f.write(encrypted_data)
        
        return file_path
    
    def decrypt_file(self, encrypted_file_path: str, output_path: Optional[str] = None) -> str:
        """
        Decrypt a file
        
        Args:
            encrypted_file_path: Path to encrypted file
            output_path: Where to save decrypted file (optional)
            
        Returns:
            Path to decrypted file
        """
        with open(encrypted_file_path, 'rb') as f:
            encrypted_data: bytes = f.read()
        
        decrypted_data: bytes = self._cipher.decrypt(encrypted_data)
        
        if not output_path:
            output_path = encrypted_file_path
        
        with open(output_path, 'wb') as f:
            f.write(decrypted_data)
        
        return output_path


# Global encryption manager instance
_encryption_manager = None


def _get_default_fallback_keys(primary_key_file: str) -> List[str]:
    repo_root: Path = Path(__file__).resolve().parents[3]
    candidates: List[str] = [
        str(repo_root / "06_enrollment_service" / "app" / "encryption.key"),
        str(repo_root / "06_enrollment_service" / "encryption.key"),
        str(repo_root / "encryption.key"),
    ]
    return [path for path in candidates if path and path != primary_key_file]


def get_encryption_manager(key_file: str = "./encryption.key") -> EncryptionManager:
    """Get or create global encryption manager instance"""
    global _encryption_manager
    env_key_file: str | None = os.getenv("ENCRYPTION_KEY_FILE")
    if env_key_file:
        key_file = env_key_file
    fallback_keys: List[str] = _get_default_fallback_keys(key_file)
    env_fallbacks: str | None = os.getenv("ENCRYPTION_KEY_FALLBACKS")
    if env_fallbacks:
        fallback_keys: List[str] = [p.strip() for p in env_fallbacks.split(";") if p.strip()]
    if _encryption_manager is None:
        _encryption_manager = EncryptionManager(key_file, fallback_keys)
    return _encryption_manager