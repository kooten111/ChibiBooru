"""
Validation utilities for API endpoints and service functions.

This module provides validation functions and helpers for common input validation tasks.
"""

from typing import List, Any, Optional


def validate_list_of_integers(value: Any, param_name: str = "parameter", allow_empty: bool = True) -> List[int]:
    """
    Validate that a value is a list of integers.
    
    Args:
        value: Value to validate
        param_name: Name of the parameter (for error messages)
        allow_empty: Whether empty lists are allowed
        
    Returns:
        List of integers
        
    Raises:
        ValueError: If validation fails
    """
    if value is None:
        if allow_empty:
            return []
        raise ValueError(f"{param_name} is required")
    
    if not isinstance(value, list):
        raise ValueError(f"{param_name} must be a list")
    
    if not allow_empty and len(value) == 0:
        raise ValueError(f"{param_name} cannot be empty")
    
    # Validate all items are integers
    try:
        result = [int(item) for item in value]
        # Check for negative values
        if any(item < 0 for item in result):
            raise ValueError(f"{param_name} contains invalid (negative) IDs")
        return result
    except (ValueError, TypeError) as e:
        raise ValueError(f"{param_name} must contain only integers") from e


def validate_string(value: Any, param_name: str = "parameter", 
                   min_length: Optional[int] = None, 
                   max_length: Optional[int] = None,
                   allow_empty: bool = False) -> str:
    """
    Validate that a value is a string with optional length constraints.
    
    Args:
        value: Value to validate
        param_name: Name of the parameter (for error messages)
        min_length: Minimum string length
        max_length: Maximum string length
        allow_empty: Whether empty strings are allowed
        
    Returns:
        Validated string
        
    Raises:
        ValueError: If validation fails
    """
    if value is None:
        if allow_empty:
            return ""
        raise ValueError(f"{param_name} is required")
    
    if not isinstance(value, str):
        raise ValueError(f"{param_name} must be a string")
    
    value = value.strip()
    
    if not allow_empty and len(value) == 0:
        raise ValueError(f"{param_name} cannot be empty")
    
    if min_length is not None and len(value) < min_length:
        raise ValueError(f"{param_name} must be at least {min_length} characters")
    
    if max_length is not None and len(value) > max_length:
        raise ValueError(f"{param_name} must be at most {max_length} characters")
    
    return value


def validate_enum(value: Any, param_name: str = "parameter", 
                 allowed_values: Optional[List[str]] = None) -> str:
    """
    Validate that a value is one of the allowed enum values.
    
    Args:
        value: Value to validate
        param_name: Name of the parameter (for error messages)
        allowed_values: List of allowed string values
        
    Returns:
        Validated string value
        
    Raises:
        ValueError: If validation fails
    """
    if value is None:
        raise ValueError(f"{param_name} is required")
    
    if not isinstance(value, str):
        raise ValueError(f"{param_name} must be a string")
    
    if allowed_values is None:
        raise ValueError("allowed_values must be provided")
    
    value = value.strip().lower()
    allowed_lower = [v.lower() for v in allowed_values]
    
    if value not in allowed_lower:
        raise ValueError(f"{param_name} must be one of: {', '.join(allowed_values)}")
    
    # Return the original case value that matches
    for allowed in allowed_values:
        if allowed.lower() == value:
            return allowed
    
    return value


def validate_integer(value: Any, param_name: str = "parameter",
                    min_value: Optional[int] = None,
                    max_value: Optional[int] = None) -> int:
    """
    Validate that a value is an integer within optional bounds.
    
    Args:
        value: Value to validate
        param_name: Name of the parameter (for error messages)
        min_value: Minimum allowed value
        max_value: Maximum allowed value
        
    Returns:
        Validated integer
        
    Raises:
        ValueError: If validation fails
    """
    if value is None:
        raise ValueError(f"{param_name} is required")
    
    try:
        result = int(value)
    except (ValueError, TypeError) as e:
        raise ValueError(f"{param_name} must be an integer") from e
    
    if min_value is not None and result < min_value:
        raise ValueError(f"{param_name} must be at least {min_value}")
    
    if max_value is not None and result > max_value:
        raise ValueError(f"{param_name} must be at most {max_value}")
    
    return result


def validate_positive_integer(value: Any, param_name: str = "parameter") -> int:
    """
    Validate that a value is a positive integer.
    
    Args:
        value: Value to validate
        param_name: Name of the parameter (for error messages)
        
    Returns:
        Validated positive integer
        
    Raises:
        ValueError: If validation fails
    """
    return validate_integer(value, param_name, min_value=1)
