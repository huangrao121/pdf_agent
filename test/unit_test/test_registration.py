"""
Tests for user registration endpoint.
"""
import pytest
from fastapi.testclient import TestClient

from main import create_app


@pytest.fixture
def app():
    """Create a test FastAPI application."""
    return create_app()


@pytest.fixture
def client(app):
    """Create a test client."""
    return TestClient(app)


class TestUserRegistrationValidation:
    """Tests for user registration validation rules."""
    
    def test_register_email_validation(self, client):
        """Test email validation."""
        # Invalid email format
        response = client.post(
            "/api/v1/auth/register",
            json={
                "email": "invalid-email",
                "username": "testuser",
                "password": "Password123",
                "full_name": "Test User"
            }
        )
        
        assert response.status_code == 422
        data = response.json()
        assert data["error"]["code"] == "VALIDATION_FAILED"
        assert "errors" in data
    
    def test_register_username_too_short(self, client):
        """Test username minimum length validation."""
        response = client.post(
            "/api/v1/auth/register",
            json={
                "email": "test@example.com",
                "username": "ab",  # Too short (min 3)
                "password": "Password123",
                "full_name": "Test User"
            }
        )
        
        assert response.status_code == 422
        data = response.json()
        assert data["error"]["code"] == "VALIDATION_FAILED"
    
    def test_register_username_invalid_chars(self, client):
        """Test username character validation."""
        response = client.post(
            "/api/v1/auth/register",
            json={
                "email": "test@example.com",
                "username": "test@user",  # Invalid character @
                "password": "Password123",
                "full_name": "Test User"
            }
        )
        
        assert response.status_code == 422
        data = response.json()
        assert data["error"]["code"] == "VALIDATION_FAILED"
        assert any("Username can only contain" in err.get("reason", "") for err in data.get("errors", []))
    
    def test_register_password_too_short(self, client):
        """Test password minimum length validation."""
        response = client.post(
            "/api/v1/auth/register",
            json={
                "email": "test@example.com",
                "username": "testuser",
                "password": "Pass1",  # Too short (min 8)
                "full_name": "Test User"
            }
        )
        
        assert response.status_code == 422
        data = response.json()
        assert data["error"]["code"] == "VALIDATION_FAILED"
    
    def test_register_password_no_letter(self, client):
        """Test password must contain letter."""
        response = client.post(
            "/api/v1/auth/register",
            json={
                "email": "test@example.com",
                "username": "testuser",
                "password": "12345678",  # No letter
                "full_name": "Test User"
            }
        )
        
        assert response.status_code == 422
        data = response.json()
        assert data["error"]["code"] == "VALIDATION_FAILED"
        assert any("at least one letter" in err.get("reason", "") for err in data.get("errors", []))
    
    def test_register_password_no_number(self, client):
        """Test password must contain number."""
        response = client.post(
            "/api/v1/auth/register",
            json={
                "email": "test@example.com",
                "username": "testuser",
                "password": "PasswordOnly",  # No number
                "full_name": "Test User"
            }
        )
        
        assert response.status_code == 422
        data = response.json()
        assert data["error"]["code"] == "VALIDATION_FAILED"
        assert any("at least one number" in err.get("reason", "") for err in data.get("errors", []))
    
    def test_register_full_name_too_long(self, client):
        """Test full name maximum length validation."""
        response = client.post(
            "/api/v1/auth/register",
            json={
                "email": "test@example.com",
                "username": "testuser",
                "password": "Password123",
                "full_name": "A" * 101  # Too long (max 100)
            }
        )
        
        assert response.status_code == 422
        data = response.json()
        assert data["error"]["code"] == "VALIDATION_FAILED"
    
    def test_register_missing_fields(self, client):
        """Test missing required fields."""
        response = client.post(
            "/api/v1/auth/register",
            json={
                "email": "test@example.com",
                # Missing username, password, full_name
            }
        )
        
        assert response.status_code == 422
        data = response.json()
        assert data["error"]["code"] == "VALIDATION_FAILED"
        assert len(data["errors"]) >= 3  # At least 3 missing fields
    
    def test_register_request_id_in_error(self, client):
        """Test that request_id is included in error responses."""
        response = client.post(
            "/api/v1/auth/register",
            json={
                "email": "invalid",
                "username": "testuser",
                "password": "Password123",
                "full_name": "Test User"
            }
        )
        
        assert response.status_code == 422
        data = response.json()
        assert "request_id" in data["error"]
        assert data["error"]["request_id"].startswith("req_")


class TestPasswordHashing:
    """Tests for password hashing functionality."""
    
    def test_password_hashing_and_verification(self):
        """Test password hashing and verification."""
        from pdf_ai_agent.security.password import hash_password, verify_password
        
        password = "Password123"
        hashed = hash_password(password)
        
        # Verify the hashed password is different from original
        assert hashed != password
        
        # Verify correct password
        assert verify_password(password, hashed) is True
        
        # Verify incorrect password
        assert verify_password("WrongPassword", hashed) is False
