class ZeekrException(Exception):
    """Base exception for the library."""


class AuthException(ZeekrException):
    """Exception for authentication errors."""
