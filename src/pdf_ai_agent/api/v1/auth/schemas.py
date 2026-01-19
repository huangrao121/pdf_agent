"""
Pydantic schemas for authentication API.
"""
from typing import Optional, List
from pydantic import BaseModel, EmailStr, Field, field_validator
import re


class RegisterRequest(BaseModel):
    """User registration request schema."""
    
    email: EmailStr = Field(..., description="User email address", max_length=254)
    username: str = Field(..., description="Username", min_length=3, max_length=30)
    password: str = Field(..., description="User password", min_length=8, max_length=72)
    full_name: str = Field(..., description="User full name", min_length=1, max_length=100)
    
    @field_validator('email')
    @classmethod
    def email_lowercase(cls, v: str) -> str:
        """Convert email to lowercase and trim."""
        return v.lower().strip()
    
    @field_validator('username')
    @classmethod
    def username_valid(cls, v: str) -> str:
        """Validate username format and trim."""
        v = v.strip()
        if not re.match(r'^[a-zA-Z0-9_.]+$', v):
            raise ValueError('Username can only contain letters, numbers, underscores, and dots')
        return v
    
    @field_validator('password')
    @classmethod
    def password_strong(cls, v: str) -> str:
        """Validate password strength."""
        if not re.search(r'[a-zA-Z]', v):
            raise ValueError('Password must contain at least one letter')
        if not re.search(r'[0-9]', v):
            raise ValueError('Password must contain at least one number')
        return v
    
    @field_validator('full_name')
    @classmethod
    def full_name_trim(cls, v: str) -> str:
        """Trim full name."""
        return v.strip()


class RegisterResponse(BaseModel):
    """User registration success response schema."""
    
    status: str = "ok"
    message: str = "registration successful"
    token: str = Field(..., description="JWT access token")
    data: dict = Field(..., description="User data")


class ErrorDetail(BaseModel):
    """Error detail for field-level errors."""
    
    field: str = Field(..., description="Field name that caused the error")
    reason: str = Field(..., description="Reason for the error")


class ErrorResponse(BaseModel):
    """Common error response schema."""
    
    error: dict = Field(..., description="Error information")
    errors: Optional[List[ErrorDetail]] = Field(default=None, description="Field-level errors")
