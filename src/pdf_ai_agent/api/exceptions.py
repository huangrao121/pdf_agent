"""
Custom exceptions for authentication and authorization.
"""


class AuthenticationError(Exception):
    """Base exception for authentication errors."""
    def __init__(self, message: str, error_code: str):
        self.message = message
        self.error_code = error_code
        super().__init__(self.message)


class InvalidCredentialsError(AuthenticationError):
    """Exception raised when credentials are invalid."""
    def __init__(self, message: str = "Invalid email or password."):
        super().__init__(message, "INVALID_CREDENTIALS")


class AccountDisabledError(AuthenticationError):
    """Exception raised when account is disabled."""
    def __init__(self, message: str = "Account is disabled."):
        super().__init__(message, "ACCOUNT_DISABLED")


class EmailNotVerifiedError(AuthenticationError):
    """Exception raised when email is not verified."""
    def __init__(self, message: str = "Email address is not verified."):
        super().__init__(message, "EMAIL_NOT_VERIFIED")


class RateLimitError(AuthenticationError):
    """Exception raised when rate limit is exceeded."""
    def __init__(self, message: str = "Too many login attempts. Please try again later.", retry_after: int = 600):
        super().__init__(message, "RATE_LIMITED")
        self.retry_after = retry_after


class ValidationError(AuthenticationError):
    """Exception raised for validation errors."""
    def __init__(self, message: str, details: dict = None):
        super().__init__(message, "VALIDATION_FAILED")
        self.details = details
