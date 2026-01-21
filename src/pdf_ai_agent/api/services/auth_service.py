"""
Authentication service for user login and credential verification.
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from pdf_ai_agent.config.database.models.model_user import UserModel
from pdf_ai_agent.config.database.models.model_auth import PasswordCredentialModel
from pdf_ai_agent.security.password_utils import verify_password, hash_password
from pdf_ai_agent.api.exceptions import (
    InvalidCredentialsError,
    AccountDisabledError,
    EmailNotVerifiedError,
    EmailTakenError,
    UsernameTakenError,
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
    
    async def get_user_by_username(self, username: str) -> Optional[UserModel]:
        """
        Get a user by username.
        
        Args:
            username: Username
            
        Returns:
            UserModel if found, None otherwise
        """
        username = username.lower().strip()
        result = await self.db_session.execute(
            select(UserModel).where(UserModel.username == username)
        )
        return result.scalar_one_or_none()
    
    async def register_user(
        self,
        email: str,
        username: str,
        password: str,
        full_name: str,
    ) -> UserModel:
        """
        Register a new user with email and password.
        
        Args:
            email: User email address
            username: Username
            password: Plain text password
            full_name: User's full name
            
        Returns:
            UserModel of created user
            
        Raises:
            EmailTakenError: If email is already in use
            UsernameTakenError: If username is already in use
        """
        # Normalize inputs
        email = email.lower().strip()
        username = username.lower().strip()
        full_name = full_name.strip()
        
        # Check if email is already registered
        existing_user = await self.get_user_by_email(email)
        if existing_user:
            raise EmailTakenError()
        
        # Check if username is already taken
        existing_username = await self.get_user_by_username(username)
        if existing_username:
            raise UsernameTakenError()
        
        # Hash the password
        password_hash = hash_password(password)
        
        # Create new user
        new_user = UserModel(
            username=username,
            email=email,
            full_name=full_name,
            is_active=True,
            is_superuser=False,
            email_verified=False,
        )
        self.db_session.add(new_user)
        await self.db_session.flush()  # Get user_id before creating password credential
        
        # Create password credential
        password_credential = PasswordCredentialModel(
            user_id=new_user.user_id,
            email=email,
            password_hash=password_hash,
            email_verified=False,
        )
        self.db_session.add(password_credential)
        
        # Commit transaction
        await self.db_session.commit()
        await self.db_session.refresh(new_user)
        
        return new_user
