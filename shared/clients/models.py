"""
Service client result models.
ServiceCallResult is used internally between clients and route handlers.
Never exposed directly to external users.
"""

from typing import Any, Optional


class ServiceCallResult:
    """
    Result returned by service client methods.
    Encapsulates success/failure and carries the payload or error details.
    This is an internal class, not exposed to external users.
    """

    def __init__(
        self,
        success: bool,
        data: Any = None,
        error_code: str = None,
        error_message: str = None,
    ):
        self.success = success
        self.data = data
        self.error_code = error_code
        self.error_message = error_message

    def __repr__(self):
        if self.success:
            return f"ServiceCallResult(success=True, data={type(self.data).__name__})"
        else:
            return f"ServiceCallResult(success=False, error={self.error_code})"
