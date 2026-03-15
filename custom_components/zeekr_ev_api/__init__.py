"""
A Python client for the Zeekr EV API.
"""

from .client import ZeekrClient
from .exceptions import AuthException, ZeekrException

__all__ = ["ZeekrClient", "ZeekrException", "AuthException"]
