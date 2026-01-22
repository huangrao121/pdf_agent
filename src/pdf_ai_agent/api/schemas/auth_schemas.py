"""
Authentication request and response schemas.
"""
from pydantic import BaseModel, EmailStr, Field, ConfigDict, field_validator
from typing import Optional
import re


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


class RegisterRequest(BaseModel):
    """User registration request schema."""
    model_config = ConfigDict(
        str_strip_whitespace=True,
    )
    
    email: EmailStr = Field(
        ...,
        description="User email address",
        max_length=254,
    )
    username: str = Field(
        ...,
        description="Username (3-30 characters, alphanumeric, underscore, dot)",
        min_length=3,
        max_length=30,
    )
    password: str = Field(
        ...,
        description="Password (8-72 characters, at least 1 letter and 1 number)",
        min_length=8,
        max_length=72,
    )
    full_name: str = Field(
        ...,
        description="Full name",
        min_length=1,
        max_length=100,
    )
    
    @field_validator('username')
    @classmethod
    def validate_username(cls, v: str) -> str:
        """Validate username format."""
        # Allow only alphanumeric characters, underscore, and dot
        if not re.match(r'^[a-zA-Z0-9_.]+$', v):
            raise ValueError('Username can only contain letters, numbers, underscore, and dot')
        return v.lower()  # Store as lowercase for uniqueness check
    
    @field_validator('password')
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        """Validate password strength."""
        # Check for at least one letter and one number
        if not re.search(r'[a-zA-Z]', v):
            raise ValueError('Password must contain at least one letter')
        if not re.search(r'\d', v):
            raise ValueError('Password must contain at least one number')
        return v


class RegisterData(BaseModel):
    """Registration data containing user info."""
    user_id: str = Field(..., description="User ID")


class RegisterResponse(BaseModel):
    """User registration success response schema."""
    status: str = Field(default="ok", description="Response status")
    message: str = Field(default="registration successful", description="Response message")
    token: str = Field(..., description="JWT access token")
    data: RegisterData


class OAuthAuthorizeRequest(BaseModel):
    """OAuth authorization request schema."""
    model_config = ConfigDict(
        str_strip_whitespace=True,
    )
    
    redirect_to: str = Field(
        default="/app",
        description="Frontend path to redirect after successful login"
    )


class OAuthAuthorizeData(BaseModel):
    """OAuth authorization data containing URL and state."""
    authorization_url: str = Field(..., description="Google OAuth authorization URL")
    provider: str = Field(default="google", description="OAuth provider")
    state: str = Field(..., description="OAuth state parameter")


class OAuthAuthorizeResponse(BaseModel):
    """OAuth authorization success response schema."""
    status: str = Field(default="ok", description="Response status")
    data: OAuthAuthorizeData


class OAuthCallbackData(BaseModel):
    """OAuth callback data containing tokens and user info."""
    access_token: str = Field(..., description="JWT access token")
    token_type: str = Field(default="Bearer", description="Token type")
    expires_in: int = Field(..., description="Token expiration time in seconds")
    refresh_token: Optional[str] = Field(None, description="Optional refresh token")
    user_id: str = Field(..., description="User ID")
    email: str = Field(..., description="User email")
    full_name: Optional[str] = Field(None, description="User full name")


class OAuthCallbackResponse(BaseModel):
    """OAuth callback success response schema."""
    status: str = Field(default="ok", description="Response status")
    message: str = Field(default="oauth login successful", description="Response message")
    data: OAuthCallbackData
