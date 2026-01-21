"""
Tests for the user registration API endpoint and components.
"""
import pytest
from pdf_ai_agent.api.schemas.auth_schemas import RegisterRequest
from pydantic import ValidationError


class TestRegistrationSchemas:
    """Tests for registration schemas."""
    
    def test_valid_registration_request(self):
        """Test valid registration request."""
        data = {
            "email": "test@example.com",
            "username": "testuser123",
            "password": "password123",
            "full_name": "Test User"
        }
        request = RegisterRequest(**data)
        
        assert request.email == "test@example.com"
        assert request.username == "testuser123"  # should be lowercased
        assert request.password == "password123"
        assert request.full_name == "Test User"
    
    def test_username_lowercase_conversion(self):
        """Test that username is converted to lowercase."""
        data = {
            "email": "test@example.com",
            "username": "TestUser123",
            "password": "password123",
            "full_name": "Test User"
        }
        request = RegisterRequest(**data)
        assert request.username == "testuser123"
    
    def test_email_validation(self):
        """Test email format validation."""
        data = {
            "email": "invalid-email",
            "username": "testuser",
            "password": "password123",
            "full_name": "Test User"
        }
        with pytest.raises(ValidationError) as exc_info:
            RegisterRequest(**data)
        
        errors = exc_info.value.errors()
        assert any("email" in str(error) for error in errors)
    
    def test_username_min_length(self):
        """Test username minimum length validation."""
        data = {
            "email": "test@example.com",
            "username": "ab",  # too short
            "password": "password123",
            "full_name": "Test User"
        }
        with pytest.raises(ValidationError) as exc_info:
            RegisterRequest(**data)
        
        errors = exc_info.value.errors()
        assert any("username" in str(error) for error in errors)
    
    def test_username_max_length(self):
        """Test username maximum length validation."""
        data = {
            "email": "test@example.com",
            "username": "a" * 31,  # too long
            "password": "password123",
            "full_name": "Test User"
        }
        with pytest.raises(ValidationError) as exc_info:
            RegisterRequest(**data)
        
        errors = exc_info.value.errors()
        assert any("username" in str(error) for error in errors)
    
    def test_username_invalid_characters(self):
        """Test username invalid characters validation."""
        data = {
            "email": "test@example.com",
            "username": "test@user",  # invalid character
            "password": "password123",
            "full_name": "Test User"
        }
        with pytest.raises(ValidationError) as exc_info:
            RegisterRequest(**data)
        
        errors = exc_info.value.errors()
        assert any("username" in str(error) for error in errors)
    
    def test_username_valid_characters(self):
        """Test username with valid characters."""
        valid_usernames = [
            "testuser",
            "test_user",
            "test.user",
            "test123",
            "test_user.123"
        ]
        
        for username in valid_usernames:
            data = {
                "email": "test@example.com",
                "username": username,
                "password": "password123",
                "full_name": "Test User"
            }
            request = RegisterRequest(**data)
            assert request.username == username.lower()
    
    def test_password_min_length(self):
        """Test password minimum length validation."""
        data = {
            "email": "test@example.com",
            "username": "testuser",
            "password": "pass1",  # too short
            "full_name": "Test User"
        }
        with pytest.raises(ValidationError) as exc_info:
            RegisterRequest(**data)
        
        errors = exc_info.value.errors()
        assert any("password" in str(error) for error in errors)
    
    def test_password_max_length(self):
        """Test password maximum length validation."""
        data = {
            "email": "test@example.com",
            "username": "testuser",
            "password": "a" * 73,  # too long
            "full_name": "Test User"
        }
        with pytest.raises(ValidationError) as exc_info:
            RegisterRequest(**data)
        
        errors = exc_info.value.errors()
        assert any("password" in str(error) for error in errors)
    
    def test_password_must_contain_letter(self):
        """Test password must contain at least one letter."""
        data = {
            "email": "test@example.com",
            "username": "testuser",
            "password": "12345678",  # no letters
            "full_name": "Test User"
        }
        with pytest.raises(ValidationError) as exc_info:
            RegisterRequest(**data)
        
        errors = exc_info.value.errors()
        assert any("letter" in str(error).lower() for error in errors)
    
    def test_password_must_contain_number(self):
        """Test password must contain at least one number."""
        data = {
            "email": "test@example.com",
            "username": "testuser",
            "password": "password",  # no numbers
            "full_name": "Test User"
        }
        with pytest.raises(ValidationError) as exc_info:
            RegisterRequest(**data)
        
        errors = exc_info.value.errors()
        assert any("number" in str(error).lower() for error in errors)
    
    def test_full_name_min_length(self):
        """Test full name minimum length validation."""
        data = {
            "email": "test@example.com",
            "username": "testuser",
            "password": "password123",
            "full_name": ""  # empty
        }
        with pytest.raises(ValidationError) as exc_info:
            RegisterRequest(**data)
        
        errors = exc_info.value.errors()
        assert any("full_name" in str(error) for error in errors)
    
    def test_full_name_max_length(self):
        """Test full name maximum length validation."""
        data = {
            "email": "test@example.com",
            "username": "testuser",
            "password": "password123",
            "full_name": "a" * 101  # too long
        }
        with pytest.raises(ValidationError) as exc_info:
            RegisterRequest(**data)
        
        errors = exc_info.value.errors()
        assert any("full_name" in str(error) for error in errors)
    
    def test_whitespace_trimming(self):
        """Test that whitespace is trimmed from inputs."""
        data = {
            "email": "  test@example.com  ",
            "username": "  testuser  ",
            "password": "password123",
            "full_name": "  Test User  "
        }
        request = RegisterRequest(**data)
        
        assert request.email == "test@example.com"
        assert request.username == "testuser"
        assert request.full_name == "Test User"
