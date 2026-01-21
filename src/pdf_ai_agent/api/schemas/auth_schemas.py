"""
Authentication request and response schemas.
"""
from pydantic import BaseModel, EmailStr, Field, ConfigDict
from typing import Optional


class LoginRequest(BaseModel):
    """Login request schema."""
    model_config = ConfigDict(
        str_strip_whitespace=True,
    )
    
    email: EmailStr = Field(..., description="User email address")
    password: str = Field(..., min_length=1, description="User password")


class LoginResponse(BaseModel):
    """Login success response schema."""
    status: str = Field(default="ok", description="Response status")
    message: str = Field(default="login successful", description="Response message")
    data: "LoginData"


class LoginData(BaseModel):
    """Login data containing tokens and user info."""
    access_token: str = Field(..., description="JWT access token")
    token_type: str = Field(default="Bearer", description="Token type")
    expires_in: int = Field(..., description="Token expiration time in seconds")
    refresh_token: Optional[str] = Field(None, description="Optional refresh token")
    user_id: str = Field(..., description="User ID")
    email: str = Field(..., description="User email")
    full_name: Optional[str] = Field(None, description="User full name")


class ErrorResponse(BaseModel):
    """Error response schema."""
    status: str = Field(default="error", description="Response status")
    error_code: str = Field(..., description="Error code")
    message: str = Field(..., description="Error message")
    details: Optional[dict] = Field(None, description="Additional error details")
