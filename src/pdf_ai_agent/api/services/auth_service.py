"""
Authentication service for user login and credential verification.
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from pdf_ai_agent.config.database.models.model_user import UserModel
from pdf_ai_agent.config.database.models.model_auth import PasswordCredentialModel
from pdf_ai_agent.security.password_utils import verify_password
from pdf_ai_agent.api.exceptions import (
    InvalidCredentialsError,
    AccountDisabledError,
    EmailNotVerifiedError,
)


class AuthService:
    """Service for handling authentication operations."""
    def __init__(self, db_session: AsyncSession):
        self.db_session = db_session

    async def authenticate_user(
        self,
        email: str,
        password: str,
        require_email_verification: bool = False
    ) -> UserModel:
        """
        Authenticate a user with email and password.
        
        Args:
            email: User email address
            password: Plain text password
            require_email_verification: Whether to require email verification
            
        Returns:
            UserModel if authentication successful
            
        Raises:
            InvalidCredentialsError: If email or password is invalid
            AccountDisabledError: If account is disabled
            EmailNotVerifiedError: If email is not verified (when required)
        """
        # Normalize email to lowercase
        email = email.lower().strip()
        
        # Query user by email
        result = await self.db_session.execute(
            select(UserModel).where(UserModel.email == email)
            .join(PasswordCredentialModel, UserModel.user_id == PasswordCredentialModel.user_id)
        )
        user = result.scalar_one_or_none()
        
        # Check if user exists and password is correct
        # Use constant-time comparison to prevent timing attacks
        if user is None or not verify_password(password, user.password_hash):
            raise InvalidCredentialsError()
        
        # Check if account is active
        if not user.is_active:
            raise AccountDisabledError()
        
        # Check email verification if required
        if require_email_verification and not user.email_verified:
            raise EmailNotVerifiedError()
        
        return user
    
    async def get_user_by_email(self, email: str) -> Optional[UserModel]:
        """
        Get a user by email address.
        
        Args:
            db: Database session
            email: User email address
            
        Returns:
            UserModel if found, None otherwise
        """
        email = email.lower().strip()
        result = await self.db_session.execute(
            select(UserModel).where(UserModel.email == email)
        )
        return result.scalar_one_or_none()
