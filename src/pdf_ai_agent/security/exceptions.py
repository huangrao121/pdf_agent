"""
Custom exceptions for JWT authentication.
"""


class JWTError(Exception):
    """Base exception for JWT-related errors."""
    pass


class TokenExpiredError(JWTError):
    """Token has expired."""
    pass


class InvalidSignatureError(JWTError):
    """Token signature is invalid."""
    pass


class InvalidIssuerError(JWTError):
    """Token issuer is invalid."""
    pass


class InvalidAudienceError(JWTError):
    """Token audience is invalid."""
    pass


class MalformedTokenError(JWTError):
    """Token is malformed or missing required claims."""
    pass


class UnknownKidError(JWTError):
    """Token kid (key ID) is unknown."""
    pass


class InvalidAlgorithmError(JWTError):
    """Token uses an invalid algorithm."""
    pass
