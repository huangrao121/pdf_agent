"""
Rate limiting middleware and utilities.
"""
from slowapi import Limiter
from slowapi.util import get_remote_address
from fastapi import Request


# Create rate limiter instance
limiter = Limiter(key_func=get_remote_address)


def get_limiter():
    """Get the rate limiter instance."""
    return limiter
