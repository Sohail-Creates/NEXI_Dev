"""
Comprehensive input validation using Pydantic.

Features:
- Type-safe data validation
- Automatic error messages  
- XSS prevention (HTML entity encoding)
- SQL injection prevention
- Prompt injection prevention (LLM)
- Directory traversal prevention
- Field-level custom validation
- Clear error reporting
"""

from typing import List, Optional, Any, Dict
from pydantic import BaseModel, Field, validator, ValidationError
import re
import html


# ============================================================================
# SECURITY VALIDATORS (Reusable)
# ============================================================================

def prevent_xss(value: str) -> str:
    """Prevent XSS attacks by escaping HTML entities."""
    if not isinstance(value, str):
        return value
    
    # Escape HTML entities
    value = html.escape(value)
    
    # Also remove script tags if somehow they slip through
    value = re.sub(r'<script[^>]*>.*?</script>', '', value, flags=re.IGNORECASE | re.DOTALL)
    
    return value.strip()


def prevent_injection(value: str) -> str:
    """Prevent common injection attacks."""
    if not isinstance(value, str):
        return value
    
    value = prevent_xss(value)
    
    # Prevent SQL injection patterns
    dangerous_sql: List[str] = [
        r"(\bunion\b.*\bselect\b)|\bor\b.*\b1\s*=\s*1",
        r"(\bdrop\b.*\btable\b)",
        r"(\binsert\b.*\binto\b)",
        r"(\bdelete\b.*\bfrom\b)",
        r"(\bupdate\b.*\bset\b)"
    ]
    
    for pattern in dangerous_sql:
        if re.search(pattern, value, re.IGNORECASE):
            raise ValueError(f"Input contains potentially malicious SQL content")
    
    return value


def prevent_prompt_injection(value: str) -> str:
    """Prevent LLM prompt injection attacks."""
    if not isinstance(value, str):
        return value
    
    value = prevent_injection(value)
    
    # Dangerous prompt injection patterns
    dangerous_patterns: List[str] = [
        r'ignore\s+previous\s+instructions',
        r'system:',
        r'<\|endoftext\|>',
        r'###\s*instruction',
        r'jailbreak',
        r'pretend.*you',
        r'you\s+are\s+now',
        r'act\s+as\s+',
        r'roleplay'
    ]
    
    for pattern in dangerous_patterns:
        if re.search(pattern, value, re.IGNORECASE):
            raise ValueError(
                f"Input contains potentially malicious prompt injection content"
            )
    
    return value


# ============================================================================
# USER & AUTHENTICATION VALIDATORS
# ============================================================================

class UserProfileValidator(BaseModel):
    """Validate user profile data."""
    
    user_id: str = Field(
        ...,
        min_length=3,
        max_length=50,
        description="Unique user identifier",
        example="sara_001"
    )
    username: str = Field(
        ...,
        min_length=2,
        max_length=50,
        description="Display name",
        example="Sara"
    )
    age: Optional[int] = Field(
        None,
        ge=1,
        le=150,
        description="User age"
    )
    
    language_preference: str = Field(
        default="english",
        pattern=r"^(english|urdu)$",
        description="Preferred language"
    )
    
    @validator('user_id')
    def validate_user_id(cls, v):
        # Only alphanumeric, underscore, hyphen
        if not re.match(r'^[a-zA-Z0-9_-]+$', v):
            raise ValueError("user_id must contain only alphanumeric characters, underscore, hyphen")
        return v.lower()
    
    @validator('username')
    def validate_username(cls, v) -> str:
        # Remove harmful content
        v: str = prevent_xss(v)
        
        # Prevent common injection attempts
        if re.search(r'[<>"\';()]', v):
            raise ValueError("username contains invalid characters")
        
        return v.strip()
    
    class Config:
        example = {
            "user_id": "sara_001",
            "username": "Sara Ahmed",
            "age": 25,
            "language_preference": "english"
        }


class AuthenticationValidator(BaseModel):
    """Validate authentication requests."""
    
    username: str = Field(
        ...,
        min_length=3,
        max_length=50,
        description="Username or email"
    )
    password: str = Field(
        ...,
        min_length=6,
        max_length=128,
        description="User password"
    )
    
    @validator('username')
    def validate_username(cls, v) -> str:
        return prevent_xss(v).strip()


# ============================================================================
# QUERY VALIDATORS
# ============================================================================

class QueryValidator(BaseModel):
    """Validate user queries."""
    
    text: str = Field(
        ...,
        min_length=1,
        max_length=1000,
        description="User query text",
        example="What is the sun?"
    )
    
    language: str = Field(
        default="english",
        pattern=r"^(english|urdu)$",
        description="Query language"
    )
    
    user_id: str = Field(
        ...,
        min_length=3,
        max_length=50,
        description="User identifier"
    )
    
    context: Optional[Dict[str, Any]] = Field(
        None,
        description="Optional context for query"
    )
    
    @validator('text')
    def validate_text(cls, v) -> str:
        # Prevent XSS and injection
        v: str = prevent_xss(v)
        
        # Check for invalid characters (but allow basic punctuation)
        if re.search(r'[<>"|\'\\]', v):
            raise ValueError("Query contains invalid characters")
        
        return v.strip()
    
    @validator('user_id')
    def validate_user_id(cls, v):
        if not re.match(r'^[a-zA-Z0-9_-]+$', v):
            raise ValueError("Invalid user_id format")
        return v
    
    class Config:
        example: Dict[str, str] = {
            "text": "What is the sun?",
            "language": "english",
            "user_id": "sara_001"
        }


# ============================================================================
# LLM REQUEST VALIDATORS
# ============================================================================

class LLMGenerateValidator(BaseModel):
    """Validate LLM generation requests."""
    
    prompt: str = Field(
        ...,
        max_length=2000,
        description="Prompt for LLM"
    )
    
    max_tokens: int = Field(
        default=128,
        ge=10,
        le=512,
        description="Maximum tokens to generate"
    )
    
    temperature: float = Field(
        default=0.6,
        ge=0.0,
        le=2.0,
        description="Sampling temperature (0=deterministic, 1=random)"
    )
    
    top_p: float = Field(
        default=0.85,
        ge=0.0,
        le=1.0,
        description="Nucleus sampling parameter"
    )
    
    @validator('prompt')
    def validate_prompt(cls, v) -> str:
        # Prevent prompt injection
        v: str = prevent_prompt_injection(v)
        return v.strip()
    
    class Config:
        example = {
            "prompt": "What is machine learning?",
            "max_tokens": 128,
            "temperature": 0.6,
            "top_p": 0.85
        }


# ============================================================================
# FILE VALIDATORS
# ============================================================================

class FilePathValidator(BaseModel):
    """Validate file paths to prevent directory traversal."""
    
    path: str = Field(
        ...,
        max_length=500,
        description="File path"
    )
    
    action: str = Field(
        default="read",
        pattern=r"^(read|write|delete)$",
        description="File operation"
    )
    
    @validator('path')
    def validate_path(cls, v):
        # Prevent directory traversal
        if '..' in v:
            raise ValueError("Path contains directory traversal (..) - not allowed")
        
        if v.startswith('/') or v.startswith('\\'):
            raise ValueError("Absolute paths not allowed")
        
        # Whitelist allowed directories
        allowed_prefixes: List[str] = ['data/', 'uploads/', 'models/', 'logs/']
        if not any(v.startswith(prefix) for prefix in allowed_prefixes):
            raise ValueError(
                f"Path must start with one of: {', '.join(allowed_prefixes)}"
            )
        
        # Ensure no special characters
        if re.search(r'[<>:"|?*\x00-\x1f]', v):
            raise ValueError("Path contains invalid characters")
        
        return v


class FileUploadValidator(BaseModel):
    """Validate file upload parameters."""
    
    filename: str = Field(
        ...,
        max_length=255,
        description="Uploaded filename"
    )
    
    size_bytes: int = Field(
        ...,
        le=100_000_000,  # 100MB max
        ge=1,
        description="File size in bytes"
    )
    
    mime_type: str = Field(
        ...,
        max_length=100,
        description="MIME type of file"
    )
    
    @validator('filename')
    def validate_filename(cls, v):
        # Remove any path components
        v = v.split('/')[-1].split('\\')[-1]
        
        # Only allow safe characters
        if not re.match(r'^[a-zA-Z0-9._-]+$', v):
            raise ValueError(
                "Filename must contain only alphanumeric, period, underscore, hyphen"
            )
        
        # Prevent dangerous extensions
        dangerous_extensions: List[str] = [
            '.exe', '.bat', '.cmd', '.com', '.pif', '.scr',
            '.vbs', '.js', '.jar', '.zip', '.rar'
        ]
        
        filename_lower = v.lower()
        if any(filename_lower.endswith(ext) for ext in dangerous_extensions):
            raise ValueError(f"File extension not allowed: {v}")
        
        return v
    
    @validator('mime_type')
    def validate_mime_type(cls, v):
        # Whitelist safe MIME types
        allowed_types: List[str] = [
            'image/jpeg', 'image/png', 'image/gif',
            'audio/mpeg', 'audio/wav', 'audio/ogg',
            'application/pdf', 'text/plain',
            'application/json'
        ]
        
        if v not in allowed_types:
            raise ValueError(f"MIME type not allowed: {v}")
        
        return v


# ============================================================================
# ENROLLMENT VALIDATORS
# ============================================================================

class EnrollmentValidator(BaseModel):
    """Validate user enrollment data."""
    
    username: str = Field(
        ...,
        min_length=2,
        max_length=50,
        description="New username"
    )
    
    age: Optional[int] = Field(
        None,
        ge=1,
        le=150,
        description="User age"
    )
    
    face_embedding: Optional[List[float]] = Field(
        None,
        min_items=128,
        max_items=512,
        description="Face embedding vector"
    )
    
    voice_embedding: Optional[List[float]] = Field(
        None,
        min_items=256,
        max_items=512,
        description="Voice embedding vector"
    )
    
    language_preference: str = Field(
        default="english",
        pattern=r"^(english|urdu)$"
    )
    
    @validator('username')
    def validate_username(cls, v) -> str:
        return prevent_xss(v).strip()
    
    @validator('face_embedding', 'voice_embedding')
    def validate_embedding(cls, v):
        if v is None:
            return v
        
        # Check for NaN and Inf
        for i, val in enumerate(v):
            if val != val:  # NaN check
                raise ValueError(f"Embedding contains NaN at index {i}")
            if abs(val) == float('inf'):
                raise ValueError(f"Embedding contains Inf at index {i}")
            # Check reasonable range
            if not (-100 <= val <= 100):
                raise ValueError(
                    f"Embedding value at index {i} out of range [-100, 100]: {val}"
                )
        
        return v


# ============================================================================
# EMBEDDING VALIDATORS
# ============================================================================

class EmbeddingValidator(BaseModel):
    """Validate embedding vectors."""
    
    embedding: List[float] = Field(
        ...,
        min_items=128,
        max_items=512,
        description="Embedding vector"
    )
    
    embedding_type: str = Field(
        ...,
        pattern=r"^(face|voice|text)$",
        description="Type of embedding"
    )
    
    @validator('embedding')
    def validate_embedding(cls, v):
        # Check for NaN, Inf
        for i, val in enumerate(v):
            if val != val:  # NaN check
                raise ValueError(f"Embedding contains NaN at index {i}")
            if abs(val) == float('inf'):
                raise ValueError(f"Embedding contains Inf at index {i}")
            
            # Check reasonable range
            if not (-100 <= val <= 100):
                raise ValueError(
                    f"Embedding value {i} out of range: {val}"
                )
        
        return v


# ============================================================================
# HEALTH CHECK & ADMIN VALIDATORS
# ============================================================================

class HealthCheckValidator(BaseModel):
    """Validate health check requests."""
    
    detailed: bool = Field(
        default=False,
        description="Include detailed service status"
    )
    
    check_dependencies: bool = Field(
        default=False,
        description="Check all service dependencies"
    )


class AdminActionValidator(BaseModel):
    """Validate administrative actions."""
    
    action: str = Field(
        ...,
        pattern=r"^(restart|clear_cache|reset_rate_limit|gc)$",
        description="Admin action to perform"
    )
    
    target: Optional[str] = Field(
        None,
        max_length=100,
        description="Target of action (e.g., service name)"
    )
    
    admin_token: str = Field(
        ...,
        description="Admin authentication token"
    )


# ============================================================================
# FACTORY FUNCTION
# ============================================================================

def validate_input(
    data: Dict[str, Any],
    validator_class: type
) -> tuple[bool, Any]:
    """
    Validate input data against a Pydantic validator.
    
    Returns:
        (is_valid, result_or_errors)
    """
    try:
        result = validator_class(**data)
        return (True, result)
    except ValidationError as e:
        return (False, e.errors())
