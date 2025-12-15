"""
Network error handling utilities for converting low-level network errors
to application-level exceptions.
"""

import re
from typing import Optional
from loguru import logger

from app.core.exceptions import (
    NetworkConnectionError,
    NetworkTimeoutError,
    NetworkSSLError,
)


def parse_rnet_error(error_str: str) -> tuple[str, str]:
    """
    Parse rnet error string to extract error type and details.

    Args:
        error_str: The error string from rnet (e.g., "wreq::Error { kind: Request, ... }")

    Returns:
        Tuple of (error_type, error_details)
    """
    # Extract kind from the error string
    kind_match = re.search(r'kind:\s*(\w+)', error_str)
    error_type = kind_match.group(1) if kind_match else "Unknown"

    # Extract more specific details
    if "SSL" in error_str or "TLS" in error_str or "certificate" in error_str.lower():
        # Extract SSL-specific error details
        reason_match = re.search(r'reason:\s*"([^"]+)"', error_str)
        if reason_match:
            return "SSL", reason_match.group(1)

        verify_match = re.search(r'verify_result:\s*Err\([^:]+:\s*"([^"]+)"', error_str)
        if verify_match:
            return "SSL", verify_match.group(1)

        return "SSL", "SSL/TLS handshake failed"

    if "TimedOut" in error_str or "timeout" in error_str.lower():
        return "Timeout", "Request timed out"

    if "Connect" in error_str or "Connection" in error_str:
        return "Connection", "Failed to establish connection"

    # Default: return the kind and a generic message
    return error_type, f"{error_type} error occurred"


def extract_url_from_error(error_str: str) -> Optional[str]:
    """
    Extract URL from error string.

    Args:
        error_str: The error string that may contain a URL

    Returns:
        The extracted URL or None
    """
    # Try to extract URI from error string
    uri_match = re.search(r'uri:\s*(https?://[^\s,}]+)', error_str)
    if uri_match:
        return uri_match.group(1)

    # Try to extract URL from different patterns
    url_match = re.search(r'(https?://[^\s,}]+)', error_str)
    if url_match:
        return url_match.group(1)

    return None


def convert_network_exception(
    exc: Exception,
    url: Optional[str] = None,
    operation: str = "request"
) -> Exception:
    """
    Convert low-level network exceptions to application-level AppError exceptions.

    Args:
        exc: The original exception
        url: The URL being accessed (if known)
        operation: The operation being performed (e.g., "request", "streaming")

    Returns:
        An AppError exception or the original exception if not recognized
    """
    error_str = str(exc)
    exc_type_name = type(exc).__name__

    # Extract URL from error string if not provided
    if not url:
        url = extract_url_from_error(error_str)
    if not url:
        url = "Unknown URL"

    logger.debug(f"Converting network exception: {exc_type_name} - {error_str}")

    # Handle rnet errors (ConnectionError, BodyError, etc.)
    if "wreq::Error" in error_str or exc_type_name in ["ConnectionError", "BodyError"]:
        error_type, error_details = parse_rnet_error(error_str)

        if error_type == "SSL":
            logger.warning(f"SSL error when accessing {url}: {error_details}")
            return NetworkSSLError(
                url=url,
                ssl_error=error_details,
                context={"operation": operation, "original_error": exc_type_name}
            )

        if error_type == "Timeout" or "TimedOut" in error_str:
            timeout_type = "body" if operation == "streaming" else "request"
            logger.warning(f"Timeout error ({timeout_type}) when accessing {url}")
            return NetworkTimeoutError(
                url=url,
                timeout_type=timeout_type,
                context={"operation": operation, "original_error": exc_type_name}
            )

        # Generic connection error
        logger.warning(f"Connection error when accessing {url}: {error_details}")
        return NetworkConnectionError(
            url=url,
            error_details=error_details,
            context={"operation": operation, "original_error": exc_type_name}
        )

    # Handle standard Python exceptions
    if exc_type_name == "TimeoutError":
        return NetworkTimeoutError(
            url=url,
            timeout_type=operation,
            context={"original_error": exc_type_name}
        )

    if exc_type_name in ["ConnectionError", "ConnectionRefusedError", "ConnectionResetError"]:
        return NetworkConnectionError(
            url=url,
            error_details=error_str,
            context={"original_error": exc_type_name}
        )

    # Return original exception if not recognized
    logger.debug(f"Network exception not recognized, returning original: {exc_type_name}")
    return exc
