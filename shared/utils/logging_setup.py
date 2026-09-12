"""
Shared Utilities - Logging Setup
Centralized logging configuration for all services
"""

import logging
import os
import re
import sys
from typing import Any, Optional


REDACTED = "[REDACTED]"
_SENSITIVE_FIELDS = re.compile(
    r"(?:authorization|api[-_]?key|secret|token|password|transcription|transcript|user_text|embedding|biometric|request[-_]?body|payload)|^(?:text|query)$",
    re.IGNORECASE,
)
_MESSAGE_PATTERNS = (
    re.compile(r"\bsk-or-v1-[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"(?<![A-Za-z0-9_-])[A-Za-z0-9_-]{43}=(?![A-Za-z0-9_=])"),
    re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~+\-/]+=*"),
    re.compile(r"(?i)((?:authorization|api[-_]?key|secret|token|password)['\"]?\s*[=:]\s*['\"]?)[^\s,;\"']+"),
    re.compile(r"(?i)((?:(?:transcription|transcript)(?:[_ ]text|\s+complete)?|transcribed(?:\s*\([^\r\n)]*\))?|transcribe\s+SUCCESS\s*-\s*text)['\"]?\s*[:=]\s*)[\s\S]+"),
    re.compile(r"(?i)((?:text|query|user_text|request[-_]?body|payload)['\"]?\s*[:=]\s*)[\s\S]+"),
    re.compile(r"(?i)(synthesizing\s+(?:speech(?:\s*\([^\r\n)]*\))?|TTS)\s*:\s*)[\s\S]+"),
    re.compile(r"(?i)(returning\s+empty\s+results\s+for\s+)[\s\S]+"),
    re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b"),
)
_BIOMETRIC_ARRAY = re.compile(r"(?i)(?:[\w_]*embeddings?|biometric)['\"]?\s*[=:]\s*\[")
_BASE_RECORD_FACTORY = logging.getLogRecordFactory()


def _redact_biometric_arrays(message: str) -> str:
    """Mask complete nested arrays, not just the first vector in a matrix."""
    for match in reversed(list(_BIOMETRIC_ARRAY.finditer(message))):
        start = match.end() - 1
        depth, quote, escaped = 0, None, False
        end = len(message)  # An incomplete array fails closed through end of message.
        for position in range(start, len(message)):
            character = message[position]
            if quote:
                if escaped:
                    escaped = False
                elif character == "\\":
                    escaped = True
                elif character == quote:
                    quote = None
            elif character in {"'", '"'}:
                quote = character
            elif character == "[":
                depth += 1
            elif character == "]":
                depth -= 1
                if depth == 0:
                    end = position + 1
                    break
        message = message[:start] + REDACTED + message[end:]
    return message


def redact(value: Any, field_name: str | None = None) -> Any:
    if field_name and _SENSITIVE_FIELDS.search(field_name):
        return REDACTED
    if isinstance(value, dict):
        return {key: redact(item, str(key)) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        redacted = [redact(item) for item in value]
        return type(value)(redacted)
    if not isinstance(value, str):
        return value
    result = value
    configured_names = (
        "NEXI_INTERNAL_SERVICE_TOKEN", "NEXI_INTERNAL_SERVICE_TOKEN_PREVIOUS",
        "NEXI_JWT_SECRET", "NEXI_JWT_SECRET_PREVIOUS", "NEXI_FERNET_KEY", "NEXI_FERNET_PREVIOUS_KEY",
        os.getenv("OPENROUTER_API_KEY_ENV", "OpenRouter_API_Key"),
        os.getenv("OPENROUTER_API_KEY_ENV", "OpenRouter_API_Key") + "_PREVIOUS",
    )
    for name in configured_names:
        secret_value = os.getenv(name, "")
        if len(secret_value) >= 8:
            result = result.replace(secret_value, REDACTED)
    for pattern in _MESSAGE_PATTERNS:
        if pattern.groups:
            result = pattern.sub(lambda match: match.group(1) + REDACTED, result)
        else:
            result = pattern.sub(REDACTED, result)
    return _redact_biometric_arrays(result)


def _redacting_record_factory(*args, **kwargs):
    record = _BASE_RECORD_FACTORY(*args, **kwargs)
    if isinstance(record.msg, dict):
        record.msg = redact(record.msg)
    if isinstance(record.args, dict):
        record.args = redact(record.args)
    elif isinstance(record.args, tuple):
        record.args = tuple(redact(value) for value in record.args)
    # Uvicorn's access formatter consumes the five structured arguments, not
    # just getMessage(). Keep its contract intact while redacting each value.
    structured_access = record.name == "uvicorn.access" and isinstance(record.args, tuple) and len(record.args) == 5
    if structured_access:
        record.msg = redact(record.msg)
    else:
        record.msg = redact(record.getMessage())
        record.args = ()
    for key in tuple(record.__dict__):
        if _SENSITIVE_FIELDS.search(key):
            setattr(record, key, REDACTED)
    from shared.utils.trace_context import get_trace_id
    correlation_id = get_trace_id()
    if correlation_id:
        if structured_access:
            record.args = (f"correlation_id={correlation_id} {record.args[0]}", *record.args[1:])
        elif "correlation_id=" not in str(record.msg):
            record.msg = f"correlation_id={correlation_id} {record.msg}"
    return record


class RedactionFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if record.exc_info:
            record.exc_text = redact(logging.Formatter().formatException(record.exc_info))
            record.exc_info = None
        for key, value in tuple(record.__dict__.items()):
            if key not in {"msg", "args"}:
                record.__dict__[key] = redact(value, key)
        return True


def install_log_redaction(enabled: bool | None = None) -> None:
    """Redact at LogRecord creation, before any handler can write a value."""
    if enabled is None:
        enabled = os.getenv("NEXI_LOG_REDACTION_ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"}
    logging.setLogRecordFactory(_redacting_record_factory if enabled else _BASE_RECORD_FACTORY)
    all_loggers = [logging.getLogger(), *(
        value for value in logging.Logger.manager.loggerDict.values() if isinstance(value, logging.Logger)
    )]
    for logger in all_loggers:
        for handler in logger.handlers:
            handler.filters = [item for item in handler.filters if not isinstance(item, RedactionFilter)]
            if enabled:
                handler.addFilter(RedactionFilter())


def setup_logging(service_name: str, level: str = "INFO") -> logging.Logger:
    """
    Setup logging for a service.
    
    Args:
        service_name: Name of the service
        level: Log level (DEBUG, INFO, WARNING, ERROR)
    
    Returns:
        Configured logger
    """
    log_level = getattr(logging, level.upper(), logging.INFO)
    
    logger = logging.getLogger(service_name)
    logger.setLevel(log_level)
    
    # Remove existing handlers
    logger.handlers = []
    
    # Create console handler
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(log_level)
    
    # Create formatter
    formatter = logging.Formatter(
        fmt=(
            "[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s"
        ),
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    
    handler.setFormatter(formatter)
    handler.addFilter(RedactionFilter())
    logger.addHandler(handler)
    
    return logger


def get_logger(name: str) -> logging.Logger:
    """Get logger for a module"""
    return logging.getLogger(name)
