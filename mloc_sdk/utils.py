"""
Utility functions for MLOC SDK.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List


def get_logger(name: str, level: str = "INFO") -> logging.Logger:
    """
    Get a configured logger instance.

    Args:
        name: Logger name
        level: Logging level (DEBUG, INFO, WARNING, ERROR)

    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)

    # Only configure if no handlers exist
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    return logger


def validate_task_spec(
    task_spec: Dict[str, Any],
    required_fields: List[str],
    raise_on_missing: bool = True
) -> bool:
    """
    Validate that required fields are present in task specification.

    Args:
        task_spec: Task specification dictionary
        required_fields: List of required field names
        raise_on_missing: Whether to raise exception on missing fields

    Returns:
        True if all required fields are present

    Raises:
        ValueError: If raise_on_missing=True and fields are missing
    """
    missing = [f for f in required_fields if f not in task_spec]

    if missing:
        if raise_on_missing:
            raise ValueError(
                f"Missing required fields in task spec: {', '.join(missing)}"
            )
        return False

    return True


def get_nested_value(data: Dict[str, Any], path: str, default: Any = None) -> Any:
    """
    Get a nested value from a dictionary using dot notation.

    Args:
        data: Dictionary to search
        path: Dot-separated path (e.g., "spec.model.name")
        default: Default value if path not found

    Returns:
        Value at path or default

    Example:
        >>> data = {"spec": {"model": {"name": "llama"}}}
        >>> get_nested_value(data, "spec.model.name")
        'llama'
    """
    keys = path.split('.')
    current = data

    for key in keys:
        if isinstance(current, dict) and key in current:
            current = current[key]
        else:
            return default

    return current


def format_error(error: Exception) -> Dict[str, Any]:
    """
    Format an exception as a JSON-serializable dictionary.

    Args:
        error: Exception to format

    Returns:
        Dictionary with error details
    """
    return {
        "error": str(error),
        "type": type(error).__name__,
    }
