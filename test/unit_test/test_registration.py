"""
Tests for the user registration API endpoint and components.
"""
import pytest

from pdf_ai_agent.api.services.auth_service import AuthService
from pdf_ai_agent.api.exceptions import (
    InvalidCredentialsError,
    AccountDisabledError,
    EmailTakenError,
    UsernameTakenError,
)
from sqlalchemy.ext.asyncio import AsyncSession


class TestAuthServiceDatabase:
    """Tests for AuthService database operations."""
    
    @pytest.mark.asyncio
    async def test_register_user_success(self, db_session: AsyncSession):
        """Test successful user registration."""
        auth_service = AuthService(db_session)
        user = await auth_service.register_user(
            email="newuser@example.com",
            username="newuser",
            password="password123",
            full_name="New User"
        )
        
        assert user.user_id is not None
        assert user.email == "newuser@example.com"
        assert user.username == "newuser"
        assert user.full_name == "New User"
        assert user.is_active is True
        assert user.is_superuser is False
        assert user.email_verified is False
    
    @pytest.mark.asyncio
    async def test_register_user_email_already_taken(self, db_session: AsyncSession):
        """Test registration fails when email is already taken."""
        auth_service = AuthService(db_session)
        # Register first user
        await auth_service.register_user(
            email="taken@example.com",
            username="user1",
            password="password123",
            full_name="User One"
        )
        
        # Try to register with same email
        with pytest.raises(EmailTakenError):
            await auth_service.register_user(
                email="taken@example.com",
                username="user2",
                password="password123",
                full_name="User Two"
            )
    
    @pytest.mark.asyncio
    async def test_register_user_username_already_taken(self, db_session: AsyncSession):
        """Test registration fails when username is already taken."""
        auth_service = AuthService(db_session)
        # Register first user
        await auth_service.register_user(
            email="user1@example.com",
            username="sameusername",
            password="password123",
            full_name="User One"
        )
        
        # Try to register with same username
        with pytest.raises(UsernameTakenError):
            await auth_service.register_user(
                email="user2@example.com",
                username="sameusername",
                password="password123",
                full_name="User Two"
            )
    
    @pytest.mark.asyncio
    async def test_register_user_creates_password_credential(
        self, 
        db_session: AsyncSession
    ):
        """Test that password credential is created with user."""
        auth_service = AuthService(db_session)
        user = await auth_service.register_user(
            email="test@example.com",
            username="testuser",
            password="password123",
            full_name="Test User"
        )
        
        # Refresh to get password credential relationship
        await db_session.refresh(user, ["password_credential"])
        
        assert user.password_credential is not None
        assert user.password_credential.email == "test@example.com"
        assert user.password_credential.email_verified is False
        # Password should be hashed, not plaintext
        assert user.password_credential.password_hash != "password123"
    
    @pytest.mark.asyncio
    async def test_get_user_by_email(self, db_session: AsyncSession):
        """Test getting user by email."""
        auth_service = AuthService(db_session)
        # Register user
        registered_user = await auth_service.register_user(
            email="findme@example.com",
            username="finduser",
            password="password123",
            full_name="Find Me"
        )
        
        # Retrieve by email
        found_user = await auth_service.get_user_by_email("findme@example.com")
        
        assert found_user is not None
        assert found_user.user_id == registered_user.user_id
        assert found_user.email == "findme@example.com"
    
    @pytest.mark.asyncio
    async def test_get_user_by_email_not_found(self, db_session: AsyncSession):
        """Test getting user by email when not found."""
        auth_service = AuthService(db_session)
        user = await auth_service.get_user_by_email("nonexistent@example.com")
        assert user is None
    
    @pytest.mark.asyncio
    async def test_get_user_by_email_case_insensitive(self, db_session: AsyncSession):
        """Test that email lookup is case-insensitive."""
        auth_service = AuthService(db_session)
        # Register user
        registered_user = await auth_service.register_user(
            email="test@example.com",
            username="testuser",
            password="password123",
            full_name="Test User"
        )
        
        # Lookup with different case
        found_user = await auth_service.get_user_by_email("TEST@EXAMPLE.COM")
        
        assert found_user is not None
        assert found_user.user_id == registered_user.user_id
    
    @pytest.mark.asyncio
    async def test_get_user_by_username(self, db_session: AsyncSession):
        """Test getting user by username."""
        auth_service = AuthService(db_session)
        # Register user
        registered_user = await auth_service.register_user(
            email="test@example.com",
            username="findableuser",
            password="password123",
            full_name="Test User"
        )
        
        # Retrieve by username
        found_user = await auth_service.get_user_by_username("findableuser")
        
        assert found_user is not None
        assert found_user.user_id == registered_user.user_id
        assert found_user.username == "findableuser"
    
    @pytest.mark.asyncio
    async def test_get_user_by_username_not_found(self, db_session: AsyncSession):
        """Test getting user by username when not found."""
        auth_service = AuthService(db_session)
        user = await auth_service.get_user_by_username("nonexistentuser")
        assert user is None
    
    @pytest.mark.asyncio
    async def test_get_user_by_username_case_insensitive(self, db_session: AsyncSession):
        """Test that username lookup is case-insensitive."""
        auth_service = AuthService(db_session)
        # Register user
        registered_user = await auth_service.register_user(
            email="test@example.com",
            username="testuser",
            password="password123",
            full_name="Test User"
        )
        
        # Lookup with different case
        found_user = await auth_service.get_user_by_username("TESTUSER")
        
        assert found_user is not None
        assert found_user.user_id == registered_user.user_id
    
    @pytest.mark.asyncio
    async def test_authenticate_user_success(self, db_session: AsyncSession):
        """Test successful user authentication."""
        auth_service = AuthService(db_session)
        # Register user
        await auth_service.register_user(
            email="auth@example.com",
            username="authuser",
            password="password123",
            full_name="Auth User"
        )
        
        # Authenticate
        user = await auth_service.authenticate_user(
            email="auth@example.com",
            password="password123",
            require_email_verification=False
        )
        
        assert user is not None
        assert user.email == "auth@example.com"
        assert user.username == "authuser"
    
    @pytest.mark.asyncio
    async def test_authenticate_user_invalid_email(self, db_session: AsyncSession):
        """Test authentication fails with invalid email."""
        auth_service = AuthService(db_session)
        with pytest.raises(InvalidCredentialsError):
            await auth_service.authenticate_user(
                email="nonexistent@example.com",
                password="password123",
                require_email_verification=False
            )
    
    @pytest.mark.asyncio
    async def test_authenticate_user_invalid_password(self, db_session: AsyncSession):
        """Test authentication fails with invalid password."""
        auth_service = AuthService(db_session)
        # Register user
        await auth_service.register_user(
            email="auth@example.com",
            username="authuser",
            password="password123",
            full_name="Auth User"
        )
        
        # Try with wrong password
        with pytest.raises(InvalidCredentialsError):
            await auth_service.authenticate_user(
                email="auth@example.com",
                password="wrongpassword",
                require_email_verification=False
            )
    
    @pytest.mark.asyncio
    async def test_authenticate_user_disabled_account(
        self, 
        db_session: AsyncSession
    ):
        """Test authentication fails for disabled account."""
        auth_service = AuthService(db_session)
        # Register user
        user = await auth_service.register_user(
            email="disabled@example.com",
            username="disableduser",
            password="password123",
            full_name="Disabled User"
        )
        
        # Disable user
        user.is_active = False
        await db_session.commit()
        
        # Try to authenticate
        with pytest.raises(AccountDisabledError):
            await auth_service.authenticate_user(
                email="disabled@example.com",
                password="password123",
                require_email_verification=False
            )
    
    @pytest.mark.asyncio
    async def test_authenticate_user_case_insensitive_email(self, db_session: AsyncSession):
        """Test that email is case-insensitive during authentication."""
        auth_service = AuthService(db_session)
        # Register user
        await auth_service.register_user(
            email="test@example.com",
            username="testuser",
            password="password123",
            full_name="Test User"
        )
        
        # Authenticate with different case
        user = await auth_service.authenticate_user(
            email="TEST@EXAMPLE.COM",
            password="password123",
            require_email_verification=False
        )
        
        assert user is not None
        assert user.email == "test@example.com"
