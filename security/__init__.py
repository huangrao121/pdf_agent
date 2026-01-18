"""
JWT Authentication Module with ES256 (ECDSA) signing.

This module provides secure JWT token generation and verification using
ECDSA (ES256) algorithm with support for key rotation.

Example usage:
    from security import KeyManager, TokenOperations
    
    # Initialize key manager
    key_manager = KeyManager.from_env()
    
    # Create token operations instance
    token_ops = TokenOperations(
        key_manager=key_manager,
        issuer="my-app",
        audience="my-api",
        leeway=10
    )
    
    # Generate a token
    token = token_ops.generate_access_token(
        user_id="user123",
        expires_in=3600,
        email="user@example.com"
    )
    
    # Verify and decode a token
    try:
        payload = token_ops.verify_and_decode_token(token)
        print(f"User ID: {payload['sub']}")
    except TokenExpiredError:
        print("Token has expired")
"""

from .exceptions import (
    JWTError,
    TokenExpiredError,
    InvalidSignatureError,
    InvalidIssuerError,
    InvalidAudienceError,
    MalformedTokenError,
    UnknownKidError,
    InvalidAlgorithmError,
)
from .key_manager import KeyManager
from .token_operations import TokenOperations

__all__ = [
    "JWTError",
    "TokenExpiredError",
    "InvalidSignatureError",
    "InvalidIssuerError",
    "InvalidAudienceError",
    "MalformedTokenError",
    "UnknownKidError",
    "InvalidAlgorithmError",
    "KeyManager",
    "TokenOperations",
]
