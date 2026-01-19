"""
Tests for the login API endpoint and authentication components.
"""
import pytest
from pdf_ai_agent.security.password_utils import hash_password, verify_password
from pdf_ai_agent.api.rate_limiter import rate_limiter


class TestPasswordUtils:
    """Tests for password utilities."""
    
    def test_password_hashing(self):
        """Test password hashing."""
        password = "test_password_123"
        hashed = hash_password(password)
        
        assert hashed != password
        assert verify_password(password, hashed)
        assert not verify_password("wrong_password", hashed)
    
    def test_different_hashes_for_same_password(self):
        """Test that same password generates different hashes (salt)."""
        password = "test_password_123"
        hash1 = hash_password(password)
        hash2 = hash_password(password)
        
        assert hash1 != hash2


class TestRateLimiter:
    """Tests for rate limiter."""
    
    def setup_method(self):
        """Clear rate limiter before each test."""
        rate_limiter._attempts.clear()
    
    def teardown_method(self):
        """Clear rate limiter after each test."""
        rate_limiter._attempts.clear()
    
    def test_rate_limiter_allows_under_limit(self):
        """Test that rate limiter allows requests under limit."""
        for i in range(4):
            is_limited, _ = rate_limiter.is_rate_limited("test_key")
            assert not is_limited
            rate_limiter.record_failed_attempt("test_key")
    
    def test_rate_limiter_blocks_over_limit(self):
        """Test that rate limiter blocks requests over limit."""
        # Record 5 failed attempts
        for i in range(5):
            rate_limiter.record_failed_attempt("test_key")
        
        # Should be rate limited
        is_limited, retry_after = rate_limiter.is_rate_limited("test_key")
        assert is_limited
        assert retry_after > 0
    
    def test_rate_limiter_clear_attempts(self):
        """Test clearing attempts."""
        # Record attempts
        for i in range(5):
            rate_limiter.record_failed_attempt("test_key")
        
        # Should be limited
        is_limited, _ = rate_limiter.is_rate_limited("test_key")
        assert is_limited
        
        # Clear attempts
        rate_limiter.clear_attempts("test_key")
        
        # Should not be limited anymore
        is_limited, _ = rate_limiter.is_rate_limited("test_key")
        assert not is_limited


class TestAuthExceptions:
    """Tests for authentication exceptions."""
    
    def test_invalid_credentials_error(self):
        """Test InvalidCredentialsError."""
        from pdf_ai_agent.api.exceptions import InvalidCredentialsError
        
        error = InvalidCredentialsError()
        assert error.error_code == "INVALID_CREDENTIALS"
        assert "Invalid email or password" in error.message
    
    def test_account_disabled_error(self):
        """Test AccountDisabledError."""
        from pdf_ai_agent.api.exceptions import AccountDisabledError
        
        error = AccountDisabledError()
        assert error.error_code == "ACCOUNT_DISABLED"
        assert "disabled" in error.message.lower()
    
    def test_rate_limit_error(self):
        """Test RateLimitError."""
        from pdf_ai_agent.api.exceptions import RateLimitError
        
        error = RateLimitError(retry_after=300)
        assert error.error_code == "RATE_LIMITED"
        assert error.retry_after == 300


class TestAuthSchemas:
    """Tests for authentication schemas."""
    
    def test_login_request_schema(self):
        """Test LoginRequest schema validation."""
        from pdf_ai_agent.api.schemas.auth_schemas import LoginRequest
        
        # Valid request
        request = LoginRequest(email="test@example.com", password="password123")
        assert request.email == "test@example.com"
        assert request.password == "password123"
    
    def test_login_request_strips_whitespace(self):
        """Test that LoginRequest strips whitespace from email."""
        from pdf_ai_agent.api.schemas.auth_schemas import LoginRequest
        
        request = LoginRequest(email="  test@example.com  ", password="password123")
        assert request.email == "test@example.com"
    
    def test_login_request_invalid_email(self):
        """Test LoginRequest with invalid email format."""
        from pdf_ai_agent.api.schemas.auth_schemas import LoginRequest
        from pydantic import ValidationError
        
        with pytest.raises(ValidationError):
            LoginRequest(email="not-an-email", password="password123")
    
    def test_login_response_schema(self):
        """Test LoginResponse schema."""
        from pdf_ai_agent.api.schemas.auth_schemas import LoginResponse, LoginData
        
        response = LoginResponse(
            status="ok",
            message="login successful",
            data=LoginData(
                access_token="token123",
                token_type="Bearer",
                expires_in=3600,
                user_id="123",
                email="test@example.com",
                full_name="Test User"
            )
        )
        
        assert response.status == "ok"
        assert response.data.access_token == "token123"
        assert response.data.expires_in == 3600
