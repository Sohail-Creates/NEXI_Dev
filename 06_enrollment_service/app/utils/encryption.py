"""
Encryption utilities for secure data storage
"""
import os
from pathlib import Path
from typing import Optional, List

from shared.credential_rotation import SecretPair
from shared.secure_storage import RotatingFernet, biometric_keys


class EncryptionManager:
    """Handles encryption and decryption of sensitive data"""
    
    def __init__(self, key_file: str = "./encryption.key", fallback_key_files: Optional[List[str]] = None) -> None:
        self.key_file: str = key_file
        self.fallback_key_files: List[str] = fallback_key_files or []
        self._rotating: RotatingFernet | None = None
        self._initialize_encryption()
    
    def _initialize_encryption(self) -> None:
        """Initialize encryption key"""
        if os.getenv("NEXI_FERNET_KEY") or os.getenv("NEXI_FERNET_KEY_FILE") or os.getenv("ENCRYPTION_KEY_FILE"):
            pair = biometric_keys()
        else:
            current = Path(self.key_file).read_text(encoding="ascii").strip()
            previous_values = {
                Path(path).read_text(encoding="ascii").strip()
                for path in self.fallback_key_files if Path(path).is_file()
            } - {current}
            if len(previous_values) > 1:
                raise RuntimeError("More than one previous Fernet key requires staged re-encryption; configure one previous key")
            pair = SecretPair(current, next(iter(previous_values), None))
        self._rotating = RotatingFernet(pair)
    
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
        
        return self._rotating.encrypt(data.encode())
    
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
        
        return self._rotating.decrypt(encrypted_data).decode()

    def is_current(self, encrypted_data: bytes) -> bool:
        return self._rotating.is_current(encrypted_data)

    def rotate_file(self, file_path: str) -> bool:
        path = Path(file_path)
        ciphertext = path.read_bytes()
        if self.is_current(ciphertext):
            return False
        rotated = self._rotating.rotate(ciphertext)
        import tempfile
        descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=path.name, suffix=".tmp")
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(rotated)
                handle.flush()
                os.fsync(handle.fileno())
            Path(temporary).replace(path)
        finally:
            Path(temporary).unlink(missing_ok=True)
        return True
    
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
        
        encrypted_data: bytes = self._rotating.encrypt(data)
        
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
        
        decrypted_data: bytes = self._rotating.decrypt(encrypted_data)
        
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
