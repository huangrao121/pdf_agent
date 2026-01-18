"""
Authentication models for user authentication and verification.

This module contains the database models for:
- OAuth identities (Google, GitHub, etc.)
- Password credentials (email + hashed password)
- Verification codes (email verification, password reset, change email)
"""

from sqlalchemy import Integer, String, Text, ForeignKey, DateTime, Boolean, Index
from sqlalchemy.orm import mapped_column, Mapped, relationship
from sqlalchemy.dialects.postgresql import BIGINT as BigInteger
from sqlalchemy import Enum
from sqlalchemy import func

from enum import Enum as PyEnum
from datetime import datetime
from typing import Optional, TYPE_CHECKING

from .model_base import Base, TimestampMixin, CreatedMixin

if TYPE_CHECKING:
    from .model_user import UserModel


class OAuthProviderEnum(PyEnum):
    """Supported OAuth providers."""
    GOOGLE = "google"
    GITHUB = "github"
    MICROSOFT = "microsoft"
    APPLE = "apple"


class OAuthIdentityModel(Base, TimestampMixin):
    """OAuth identity model - stores OAuth login credentials.
    
    Represents a user's identity from an OAuth provider (Google, GitHub, etc.).
    A user can have multiple OAuth identities linked to their account.
    
    Design considerations:
    - (provider, provider_subject) is unique - one provider account = one identity
    - provider_subject is the unique identifier from the OAuth provider (e.g., Google user ID)
    - access_token and refresh_token should be encrypted at rest in production
    - Supports linking multiple OAuth providers to one user account
    """
    __tablename__ = 'oauth_identities'
    __table_args__ = (
        # Composite unique index: one OAuth account can only link to one user
        Index('idx_oauth_provider_subject', 'provider', 'provider_subject', unique=True),
    )

    # Primary key
    oauth_identity_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    
    # Foreign key - linked user
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey('users.user_id'), nullable=False, index=True)

    # OAuth provider information
    provider: Mapped[str] = mapped_column(
        Enum(OAuthProviderEnum, values_callable=lambda x: [e.value for e in x]),
        nullable=False
    )  # OAuth provider: google, github, microsoft, apple
    provider_subject: Mapped[str] = mapped_column(String(255), nullable=False)  # Unique user ID from provider
    provider_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)  # Email from provider (may change)
    provider_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)  # Display name from provider

    # OAuth tokens (should be encrypted in production)
    access_token: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # OAuth access token
    refresh_token: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # OAuth refresh token
    token_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)  # Access token expiry

    # Relationships
    user: Mapped["UserModel"] = relationship(
        "UserModel",
        back_populates="oauth_identities"
    )


class PasswordCredentialModel(Base, TimestampMixin):
    """Password credential model - stores email and hashed password for authentication.
    
    Represents email/password login credentials for a user.
    A user can only have one password credential record.
    
    Design considerations:
    - password_hash stores ONLY hashed passwords (e.g., bcrypt, argon2)
    - NEVER store plaintext passwords
    - email_verified tracks whether the email has been verified
    - last_password_change_at helps enforce password rotation policies
    """
    __tablename__ = 'password_credentials'

    # Primary key (also FK to users table - 1:1 relationship)
    user_id: Mapped[int] = mapped_column(
        BigInteger, 
        ForeignKey('users.user_id'), 
        primary_key=True
    )

    # Email for login (duplicates users.email, but allows email to be optional in users table)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    
    # Password storage (ONLY hashed values)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)  # Hashed password (bcrypt/argon2)
    
    # Email verification status
    email_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    email_verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # Password management
    last_password_change_at: Mapped[datetime] = mapped_column(
        DateTime, 
        nullable=False, 
        server_default=func.now()
    )  # Track password changes

    # Relationships
    user: Mapped["UserModel"] = relationship(
        "UserModel",
        back_populates="password_credential"
    )


class VerificationCodeTypeEnum(PyEnum):
    """Types of verification codes."""
    EMAIL_VERIFICATION = "email_verification"  # Verify email address during registration
    PASSWORD_RESET = "password_reset"  # Reset forgotten password
    CHANGE_EMAIL = "change_email"  # Verify new email address when changing


class VerificationCodeModel(Base, CreatedMixin):
    """Verification code model - unified table for all verification flows.
    
    Stores verification tokens for:
    - Email verification (after registration)
    - Password reset (forgot password flow)
    - Email change (verify new email address)
    
    Design considerations:
    - code_hash stores ONLY hashed tokens (use SHA256 or similar)
    - NEVER store plaintext verification codes in database
    - expires_at enforces time-limited validity (e.g., 15 minutes to 24 hours)
    - used_at tracks when code was consumed (one-time use)
    - type field distinguishes between different verification purposes
    - new_email field is used only for CHANGE_EMAIL type
    """
    __tablename__ = 'verification_codes'
    __table_args__ = (
        # Index for efficient lookup by user and type
        Index('idx_verification_user_type', 'user_id', 'code_type'),
        # Index for efficient cleanup of expired codes
        Index('idx_verification_expires_at', 'expires_at'),
    )

    # Primary key
    verification_code_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    
    # Foreign key - user this code belongs to
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey('users.user_id'), nullable=False, index=True)

    # Verification code information
    code_type: Mapped[str] = mapped_column(
        Enum(VerificationCodeTypeEnum, values_callable=lambda x: [e.value for e in x]),
        nullable=False
    )  # Type: email_verification, password_reset, change_email
    
    code_hash: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)  # Hashed code (SHA256)
    
    # Expiration and usage tracking
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)  # Code expiry time
    used_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)  # When code was used (NULL = not used)
    
    # Additional data for specific code types
    new_email: Mapped[Optional[str]] = mapped_column(
        String(255), 
        nullable=True
    )  # For CHANGE_EMAIL type: the new email address being verified
    
    # Relationships
    user: Mapped["UserModel"] = relationship(
        "UserModel",
        back_populates="verification_codes"
    )
