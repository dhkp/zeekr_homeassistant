import importlib
import logging
from typing import Dict, Any, Optional

from .const import (
    CONF_HMAC_ACCESS_KEY,
    CONF_HMAC_SECRET_KEY,
    CONF_PASSWORD_PUBLIC_KEY,
    CONF_PROD_SECRET,
    CONF_VIN_IV,
    CONF_VIN_KEY,
)

_LOGGER = logging.getLogger(__name__)


def get_zeekr_client_class(use_local: bool = False):
    """Dynamically import ZeekrClient from local or installed package."""
    if use_local:
        try:
            module = importlib.import_module("custom_components.zeekr_ev_api.client")
            _LOGGER.debug("Using local zeekr_ev_api from custom_components")
            return module.ZeekrClient
        except ImportError as ex:
            raise ImportError(
                "Local zeekr_ev_api not found in custom_components. "
                "Please install it or disable 'Use local API' option."
            ) from ex

    # Try to import from installed package (pip)
    try:
        module = importlib.import_module("zeekr_ev_api.client")
        _LOGGER.debug("Using installed zeekr_ev_api package")
        return module.ZeekrClient
    except ImportError as ex:
        raise ImportError(
            "zeekr_ev_api package not installed. "
            "Please install it via pip or enable 'Use local API' option."
        ) from ex


def validate_input(user_input: Dict[str, Any]) -> Optional[str]:
    """Validate user input format and length.

    Accepts both base64-encoded secrets (CN/AU) and hex/ASCII secrets (EU).
    Validation only checks that values are non-empty strings of a reasonable length.
    """

    def check_field(key, min_len=None, allowed_lens=None):
        """Strip, update, and length-check a single field.

        Args:
            key: The field key in user_input.
            min_len: Minimum acceptable length (inclusive).
            allowed_lens: List/set of exact lengths that are acceptable.
                          If provided, the value length must be one of these.
        """
        val = user_input.get(key, "").strip()
        # Store stripped value back
        user_input[key] = val

        if not val:
            return None  # Optional fields may be empty

        if min_len and len(val) < min_len:
            return f"invalid_length_min_{min_len}_{key}"

        if allowed_lens and len(val) not in allowed_lens:
            return f"invalid_length_{key}"

        return None

    # Validate HMAC Access Key (>= 32)
    if err := check_field(CONF_HMAC_ACCESS_KEY, min_len=32):
        return err

    # Validate HMAC Secret Key (>= 32)
    if err := check_field(CONF_HMAC_SECRET_KEY, min_len=32):
        return err

    # Validate Password Public Key (>= 200)
    if err := check_field(CONF_PASSWORD_PUBLIC_KEY, min_len=200):
        return err

    # Validate Prod Secret: 32 chars (EU hex) or 40 chars (other encodings)
    if err := check_field(CONF_PROD_SECRET, allowed_lens={32, 40}):
        return err

    # Validate VIN Key: 16 chars (ASCII raw key) or 32 chars (hex-encoded key)
    if err := check_field(CONF_VIN_KEY, allowed_lens={16, 32}):
        return err

    # Validate VIN IV: 16 chars (ASCII raw IV) or 32 chars (hex-encoded IV)
    if err := check_field(CONF_VIN_IV, allowed_lens={16, 32}):
        return err

    return None
