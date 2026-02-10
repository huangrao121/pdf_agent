"""
Authentication service for user login and credential verification.
"""
import secrets
import hashlib
import base64
import json
import logging
from urllib.parse import urlencode
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any, Tuple
import httpx

from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token

from pdf_ai_agent.config.database.models.model_user import UserModel
from pdf_ai_agent.config.database.models.model_auth import PasswordCredentialModel, OAuthIdentityModel
from pdf_ai_agent.security.password_utils import verify_password, hash_password
from pdf_ai_agent.api.exceptions import (
    InvalidCredentialsError,
    AccountDisabledError,
    EmailNotVerifiedError,
    EmailTakenError,
    UsernameTakenError,
    OAuthProviderError,
    InvalidIdTokenError,
)

logger = logging.getLogger(__name__)


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
        
        # Query password credential by email to get password_hash
        result = await self.db_session.execute(
            select(PasswordCredentialModel).where(PasswordCredentialModel.email == email)
        )
        password_credential = result.scalar_one_or_none()
        
        # Check if credential exists and password is correct
        # Use constant-time comparison to prevent timing attacks
        if password_credential is None or not verify_password(password, password_credential.password_hash):
            raise InvalidCredentialsError()
        
        # Query user by user_id from password credential
        result = await self.db_session.execute(
            select(UserModel).where(UserModel.user_id == password_credential.user_id)
        )
        user = result.scalar_one_or_none()
        
        if user is None:
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
        # Note: Both UserModel and PasswordCredentialModel maintain email_verified fields
        # UserModel.email_verified: General account email verification status
        # PasswordCredentialModel.email_verified: Specific to this email-password credential
        # They should be kept in sync for email-password auth
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
    
    def validate_redirect_to(self, redirect_to: str, allowed_prefixes: list) -> bool:
        """
        Validate redirect_to parameter against allowlist.
        
        Args:
            redirect_to: The redirect path to validate
            allowed_prefixes: List of allowed path prefixes
            
        Returns:
            True if valid, False otherwise
        """
        # Reject URLs with protocol (http://, https://, //, etc.)
        if "://" in redirect_to or redirect_to.startswith("//"):
            return False
        
        # Check if redirect_to starts with any allowed prefix
        return any(redirect_to.startswith(prefix) for prefix in allowed_prefixes)
    
    def generate_state(self) -> str:
        """
        Generate a random state parameter for OAuth.
        
        Returns:
            Random state string with 'st_' prefix
        """
        random_part = secrets.token_urlsafe(32)
        return f"st_{random_part}"
    
    def generate_pkce_pair(self) -> tuple:
        """
        Generate PKCE code_verifier and code_challenge.
        
        Returns:
            Tuple of (code_verifier, code_challenge)
        """
        # Generate code_verifier (43-128 characters)
        code_verifier = secrets.token_urlsafe(64)
        
        # Generate code_challenge using S256 method
        code_challenge_bytes = hashlib.sha256(code_verifier.encode('utf-8')).digest()
        code_challenge = base64.urlsafe_b64encode(code_challenge_bytes).decode('utf-8').rstrip('=')
        
        return code_verifier, code_challenge
    
    def build_authorization_url(
        self,
        client_id: str,
        redirect_uri: str,
        scope: str,
        state: str,
        auth_endpoint: str,
        code_challenge: str = None,
    ) -> str:
        """
        Build Google OAuth authorization URL.
        
        Args:
            client_id: Google OAuth client ID
            redirect_uri: Redirect URI
            scope: OAuth scopes
            state: State parameter
            auth_endpoint: Authorization endpoint URL
            code_challenge: Optional PKCE code challenge
            
        Returns:
            Complete authorization URL
        """
        params = {
            'client_id': client_id,
            'redirect_uri': redirect_uri,
            'response_type': 'code',
            'scope': scope,
            'state': state,
        }
        
        if code_challenge:
            params['code_challenge'] = code_challenge
            params['code_challenge_method'] = 'S256'
        
        query_string = urlencode(params)
        return f"{auth_endpoint}?{query_string}"
    
    async def exchange_code_for_tokens(
        self,
        code: str,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        token_endpoint: str,
        code_verifier: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Exchange authorization code for tokens from Google.
        
        Args:
            code: Authorization code from OAuth callback
            client_id: Google OAuth client ID
            client_secret: Google OAuth client secret
            redirect_uri: Redirect URI
            token_endpoint: Google token endpoint URL
            code_verifier: Optional PKCE code verifier
            
        Returns:
            Dictionary containing access_token, id_token, etc.
            
        Raises:
            OAuthProviderError: If token exchange fails
        """
        data = {
            'code': code,
            'client_id': client_id,
            'client_secret': client_secret,
            'redirect_uri': redirect_uri,
            'grant_type': 'authorization_code',
        }
        
        if code_verifier:
            data['code_verifier'] = code_verifier
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    token_endpoint,
                    data=data,
                    headers={'Content-Type': 'application/x-www-form-urlencoded'},
                    timeout=10.0,
                )
                
                if response.status_code != 200:
                    error_data = response.json() if response.headers.get('content-type', '').startswith('application/json') else {}
                    error_msg = error_data.get('error_description', error_data.get('error', 'Token exchange failed'))
                    raise OAuthProviderError(f"Failed to exchange code for tokens: {error_msg}")
                
                return response.json()
        except httpx.HTTPError as e:
            logger.error(f"HTTP error during token exchange: {e}", exc_info=True)
            raise OAuthProviderError(f"Failed to exchange code for tokens: {str(e)}")
    
    def verify_and_decode_id_token(
        self,
        id_token: str,
        client_id: str,
    ) -> Dict[str, Any]:
        """
        Verify and decode Google ID token (JWT).
        
        This is a simplified implementation that decodes the JWT without full signature verification.
        In production, you should use google-auth library for proper verification.
        
        Args:
            id_token: Google ID token (JWT)
            client_id: Expected audience (client_id)
            
        Returns:
            Dictionary containing user claims (sub, email, name, picture, etc.)
            
        Raises:
            InvalidIdTokenError: If token is invalid or verification fails
        """
        try:
            request = google_requests.Request()
            id_info = google_id_token.verify_oauth2_token(id_token, request, client_id)
            
            if id_info.get('iss') not in ['accounts.google.com', 'https://accounts.google.com']:
                raise InvalidIdTokenError("Invalid issuer in ID token")
            return id_info
        except (ValueError, KeyError, json.JSONDecodeError) as e:
            logger.error(f"ID token verification failed: {e}", exc_info=True)
            raise InvalidIdTokenError(f"Failed to verify ID token: {str(e)}")
    
    async def handle_oauth_user(
        self,
        provider: str,
        provider_subject: str,
        provider_email: Optional[str],
        provider_name: Optional[str],
        avatar_url: Optional[str] = None,
        access_token: Optional[str] = None,
        refresh_token: Optional[str] = None,
    ) -> Tuple[UserModel, bool]:
        """
        Handle OAuth user creation or linking.
        
        Three scenarios:
        1. OAuth identity exists -> Login existing user (may update user info)
        2. OAuth identity doesn't exist, but email exists -> Link to existing user
        3. OAuth identity doesn't exist, email doesn't exist -> Create new user
        
        Args:
            provider: OAuth provider name (e.g., 'google')
            provider_subject: Provider's unique user ID (e.g., Google sub)
            provider_email: Email from provider
            provider_name: Display name from provider
            avatar_url: Avatar URL from provider
            access_token: OAuth access token
            refresh_token: OAuth refresh token
            
        Returns:
            Tuple of (UserModel, is_new_user)
            
        Raises:
            Exception: If database operation fails
        """
        # Scenario 1: OAuth identity already exists
        result = await self.db_session.execute(
            select(OAuthIdentityModel).where(
                OAuthIdentityModel.provider == provider,
                OAuthIdentityModel.provider_subject == provider_subject
            )
        )
        oauth_identity = result.scalar_one_or_none()
        
        if oauth_identity:
            # Get existing user
            result = await self.db_session.execute(
                select(UserModel).where(UserModel.user_id == oauth_identity.user_id)
            )
            user = result.scalar_one_or_none()
            
            if not user:
                logger.error(f"OAuth identity exists but user not found for identity ID {oauth_identity.oauth_identity_id}")
                raise InvalidCredentialsError("User account not found")
            
            # Update user info if changed
            if provider_name and user.full_name != provider_name:
                user.full_name = provider_name
            if avatar_url and user.avatar_url != avatar_url:
                user.avatar_url = avatar_url
            
            # Update OAuth identity tokens
            oauth_identity.provider_email = provider_email
            oauth_identity.provider_name = provider_name
            oauth_identity.access_token = access_token
            oauth_identity.refresh_token = refresh_token
            
            await self.db_session.commit()
            await self.db_session.refresh(user)
            
            return user, False
        
        # Scenario 2 & 3: OAuth identity doesn't exist
        # Check if user with this email already exists
        existing_user = None
        if provider_email:
            existing_user = await self.get_user_by_email(provider_email)
        
        if existing_user:
            # Scenario 2: Link OAuth identity to existing user
            user = existing_user
            
            # Update user info if not set
            if provider_name and not user.full_name:
                user.full_name = provider_name
            if avatar_url and not user.avatar_url:
                user.avatar_url = avatar_url
        else:
            # Scenario 3: Create new user
            # Generate a unique username from email or provider_subject
            username = self._generate_username_from_email(provider_email) if provider_email else f"user_{provider_subject[:8]}"
            
            # Ensure username is unique
            counter = 1
            original_username = username
            while await self.get_user_by_username(username):
                username = f"{original_username}{counter}"
                counter += 1
            
            user = UserModel(
                username=username,
                email=provider_email,
                full_name=provider_name or "User",
                avatar_url=avatar_url,
                is_active=True,
                is_superuser=False,
                email_verified=True,  # Email from OAuth provider is assumed verified
            )
            self.db_session.add(user)
            await self.db_session.flush()  # Get user_id
        
        # Create OAuth identity
        new_oauth_identity = OAuthIdentityModel(
            user_id=user.user_id,
            provider=provider,
            provider_subject=provider_subject,
            provider_email=provider_email,
            provider_name=provider_name,
            access_token=access_token,
            refresh_token=refresh_token,
        )
        self.db_session.add(new_oauth_identity)
        
        await self.db_session.commit()
        await self.db_session.refresh(user)
        
        return user, not existing_user
    
    def _generate_username_from_email(self, email: str) -> str:
        """
        Generate username from email address.
        
        Args:
            email: Email address
            
        Returns:
            Username derived from email
        """
        if not email or '@' not in email:
            return f"user_{secrets.token_hex(4)}"
        
        # Extract local part of email
        local_part = email.split('@')[0]
        
        # Clean up: keep only alphanumeric and underscore
        username = ''.join(c if c.isalnum() or c == '_' else '_' for c in local_part)
        
        # Ensure it's not too long
        if len(username) > 20:
            username = username[:20]
        
        return username.lower()
