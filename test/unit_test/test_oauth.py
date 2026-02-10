"""
Tests for OAuth authorization endpoint.
"""
import pytest
import os
from unittest.mock import patch, MagicMock
from pdf_ai_agent.api.services.auth_service import AuthService


class TestOAuthService:
    """Tests for OAuth service methods."""
    
    def test_validate_redirect_to_valid(self, db_session):
        """Test redirect_to validation with valid paths."""
        service = AuthService(db_session=db_session)
        allowed_prefixes = ["/", "/app", "/settings"]
        
        assert service.validate_redirect_to("/", allowed_prefixes)
        assert service.validate_redirect_to("/app", allowed_prefixes)
        assert service.validate_redirect_to("/app/dashboard", allowed_prefixes)
        assert service.validate_redirect_to("/settings/profile", allowed_prefixes)
    
    def test_validate_redirect_to_invalid(self, db_session):
        """Test redirect_to validation with invalid paths."""
        service = AuthService(db_session=db_session)
        allowed_prefixes = ["/", "/app", "/settings"]
        
        assert not service.validate_redirect_to("https://evil.com", allowed_prefixes)
        assert not service.validate_redirect_to("http://example.com/app", allowed_prefixes)
        assert not service.validate_redirect_to("//evil.com", allowed_prefixes)
    
    def test_generate_state(self, db_session):
        """Test state generation."""
        service = AuthService(db_session=db_session)
        
        state1 = service.generate_state()
        state2 = service.generate_state()
        
        assert state1.startswith("st_")
        assert state2.startswith("st_")
        assert state1 != state2
        assert len(state1) > 10
    
    def test_generate_pkce_pair(self, db_session):
        """Test PKCE code_verifier and code_challenge generation."""
        service = AuthService(db_session=db_session)
        
        verifier, challenge = service.generate_pkce_pair()
        
        assert len(verifier) > 40
        assert len(challenge) > 40
        assert verifier != challenge
    
    def test_build_authorization_url(self, db_session):
        """Test authorization URL building."""
        service = AuthService(db_session=db_session)
        
        url = service.build_authorization_url(
            client_id="test_client_id",
            redirect_uri="http://localhost:8000/callback",
            scope="openid email profile",
            state="st_test123",
            auth_endpoint="https://accounts.google.com/o/oauth2/v2/auth",
        )
        
        assert "https://accounts.google.com/o/oauth2/v2/auth?" in url
        assert "client_id=test_client_id" in url
        assert "redirect_uri=http" in url
        assert "response_type=code" in url
        assert "scope=openid" in url
        assert "state=st_test123" in url
    
    def test_build_authorization_url_with_pkce(self, db_session):
        """Test authorization URL building with PKCE."""
        service = AuthService(db_session=db_session)
        
        url = service.build_authorization_url(
            client_id="test_client_id",
            redirect_uri="http://localhost:8000/callback",
            scope="openid email profile",
            state="st_test123",
            auth_endpoint="https://accounts.google.com/o/oauth2/v2/auth",
            code_challenge="test_challenge",
        )
        
        assert "code_challenge=test_challenge" in url
        assert "code_challenge_method=S256" in url


class TestOAuthAuthorizeEndpoint:
    """Tests for OAuth authorization endpoint - service layer only."""
    
    def test_oauth_config_from_env(self):
        """Test loading OAuth config from environment."""
        with patch.dict(os.environ, {
            "GOOGLE_CLIENT_ID": "test_client_id",
            "GOOGLE_CLIENT_SECRET": "test_client_secret",
            "GOOGLE_REDIRECT_URI": "http://localhost:8000/callback",
            "GOOGLE_SCOPES": "openid email profile",
            "OAUTH_ENABLED": "true",
            "OAUTH_ALLOWED_REDIRECT_TO_PREFIXES": "/,/app,/settings",
        }):
            from pdf_ai_agent.config.oauth_config import OAuthConfig
            
            config = OAuthConfig.from_env()
            
            assert config.google_client_id == "test_client_id"
            assert config.google_client_secret == "test_client_secret"
            assert config.google_redirect_uri == "http://localhost:8000/callback"
            assert config.oauth_enabled is True
            assert "/app" in config.oauth_allowed_redirect_to_prefixes
    
    def test_app_config_default(self):
        """Test default app config."""
        from pdf_ai_agent.config.app_config import AppConfig
        
        config = AppConfig.from_yaml("nonexistent.yaml")
        
        assert config.oauth_state_ttl_seconds == 600
        assert config.oauth_pkce_enabled is True


class TestOAuthCallbackService:
    """Tests for OAuth callback service methods."""
    
    @pytest.mark.asyncio
    async def test_exchange_code_for_tokens_success(self, db_session):
        """Test successful token exchange."""
        service = AuthService(db_session=db_session)
        
        # Mock httpx response
        mock_response_data = {
            "access_token": "mock_access_token",
            "id_token": "mock_id_token",
            "expires_in": 3600,
            "token_type": "Bearer",
        }
        
        with patch("httpx.AsyncClient.post") as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = mock_response_data
            mock_post.return_value = mock_response
            
            result = await service.exchange_code_for_tokens(
                code="test_code",
                client_id="test_client_id",
                client_secret="test_secret",
                redirect_uri="http://localhost:8000/callback",
                token_endpoint="https://oauth2.googleapis.com/token",
            )
            
            assert result["access_token"] == "mock_access_token"
            assert result["id_token"] == "mock_id_token"
    
    @pytest.mark.asyncio
    async def test_exchange_code_for_tokens_with_pkce(self, db_session):
        """Test token exchange with PKCE verifier."""
        service = AuthService(db_session=db_session)
        
        mock_response_data = {
            "access_token": "mock_access_token",
            "id_token": "mock_id_token",
        }
        
        with patch("httpx.AsyncClient.post") as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = mock_response_data
            mock_post.return_value = mock_response
            
            await service.exchange_code_for_tokens(
                code="test_code",
                client_id="test_client_id",
                client_secret="test_secret",
                redirect_uri="http://localhost:8000/callback",
                token_endpoint="https://oauth2.googleapis.com/token",
                code_verifier="test_verifier",
            )
            
            # Verify PKCE verifier was included in request
            call_kwargs = mock_post.call_args[1]
            assert "code_verifier" in call_kwargs["data"]
    
    @pytest.mark.asyncio
    async def test_exchange_code_for_tokens_error(self, db_session):
        """Test token exchange with error response."""
        service = AuthService(db_session=db_session)
        
        with patch("httpx.AsyncClient.post") as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 400
            mock_response.headers.get.return_value = "application/json"
            mock_response.json.return_value = {
                "error": "invalid_grant",
                "error_description": "Invalid authorization code"
            }
            mock_post.return_value = mock_response
            
            from pdf_ai_agent.api.exceptions import OAuthProviderError
            
            with pytest.raises(OAuthProviderError):
                await service.exchange_code_for_tokens(
                    code="invalid_code",
                    client_id="test_client_id",
                    client_secret="test_secret",
                    redirect_uri="http://localhost:8000/callback",
                    token_endpoint="https://oauth2.googleapis.com/token",
                )
    
    def test_verify_id_token_success(self, db_session):
        """Test ID token verification with valid token."""
        service = AuthService(db_session=db_session)
        
        # Create a mock ID token (simplified - only payload)
        import json
        import base64
        import time
        
        payload = {
            "sub": "12345",
            "email": "test@example.com",
            "email_verified": True,
            "name": "Test User",
            "picture": "https://example.com/photo.jpg",
            "aud": "test_client_id",
            "iss": "https://accounts.google.com",
            "exp": int(time.time()) + 3600,
        }
        
        # Create fake JWT (header.payload.signature)
        header = base64.urlsafe_b64encode(json.dumps({"alg": "RS256", "typ": "JWT"}).encode()).decode().rstrip("=")
        payload_b64 = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
        signature = base64.urlsafe_b64encode(b"fake_signature").decode().rstrip("=")
        id_token = f"{header}.{payload_b64}.{signature}"
        
        result = service.verify_and_decode_id_token(
            id_token=id_token,
            client_id="test_client_id",
        )
        
        assert result["sub"] == "12345"
        assert result["email"] == "test@example.com"
        assert result["name"] == "Test User"
    
    def test_verify_id_token_invalid_audience(self, db_session):
        """Test ID token verification with invalid audience."""
        service = AuthService(db_session=db_session)
        
        import json
        import base64
        import time
        
        payload = {
            "sub": "12345",
            "aud": "wrong_client_id",
            "iss": "https://accounts.google.com",
            "exp": int(time.time()) + 3600,
        }
        
        header = base64.urlsafe_b64encode(json.dumps({"alg": "RS256"}).encode()).decode().rstrip("=")
        payload_b64 = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
        signature = base64.urlsafe_b64encode(b"fake_signature").decode().rstrip("=")
        id_token = f"{header}.{payload_b64}.{signature}"
        
        from pdf_ai_agent.api.exceptions import InvalidIdTokenError
        
        with pytest.raises(InvalidIdTokenError, match="Invalid audience"):
            service.verify_and_decode_id_token(
                id_token=id_token,
                client_id="test_client_id",
            )
    
    def test_verify_id_token_expired(self, db_session):
        """Test ID token verification with expired token."""
        service = AuthService(db_session=db_session)
        
        import json
        import base64
        import time
        
        payload = {
            "sub": "12345",
            "aud": "test_client_id",
            "iss": "https://accounts.google.com",
            "exp": int(time.time()) - 3600,  # Expired 1 hour ago
        }
        
        header = base64.urlsafe_b64encode(json.dumps({"alg": "RS256"}).encode()).decode().rstrip("=")
        payload_b64 = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
        signature = base64.urlsafe_b64encode(b"fake_signature").decode().rstrip("=")
        id_token = f"{header}.{payload_b64}.{signature}"
        
        from pdf_ai_agent.api.exceptions import InvalidIdTokenError
        
        with pytest.raises(InvalidIdTokenError, match="Token expired"):
            service.verify_and_decode_id_token(
                id_token=id_token,
                client_id="test_client_id",
            )
    
    @pytest.mark.asyncio
    async def test_handle_oauth_user_existing_identity(self, db_session):
        """Test OAuth user handling with existing identity."""
        from pdf_ai_agent.config.database.models.model_user import UserModel
        from pdf_ai_agent.config.database.models.model_auth import OAuthIdentityModel
        
        # Create existing user and OAuth identity
        user = UserModel(
            username="testuser",
            email="test@example.com",
            full_name="Test User",
            is_active=True,
        )
        db_session.add(user)
        await db_session.flush()
        
        oauth_identity = OAuthIdentityModel(
            user_id=user.user_id,
            provider="google",
            provider_subject="12345",
            provider_email="test@example.com",
        )
        db_session.add(oauth_identity)
        await db_session.commit()
        
        service = AuthService(db_session=db_session)
        
        # Handle OAuth user (should return existing user)
        result_user, is_new = await service.handle_oauth_user(
            provider="google",
            provider_subject="12345",
            provider_email="test@example.com",
            provider_name="Test User Updated",
        )
        
        assert result_user.user_id == user.user_id
        assert is_new is False
        assert result_user.full_name == "Test User Updated"
    
    @pytest.mark.asyncio
    async def test_handle_oauth_user_link_existing_email(self, db_session):
        """Test OAuth user handling - link to existing email."""
        from pdf_ai_agent.config.database.models.model_user import UserModel
        
        # Create existing user with email (no OAuth identity yet)
        user = UserModel(
            username="existinguser",
            email="existing@example.com",
            full_name="Existing User",
            is_active=True,
        )
        db_session.add(user)
        await db_session.commit()
        
        service = AuthService(db_session=db_session)
        
        # Handle OAuth user (should link to existing user)
        result_user, is_new = await service.handle_oauth_user(
            provider="google",
            provider_subject="67890",
            provider_email="existing@example.com",
            provider_name="Google Name",
        )
        
        assert result_user.user_id == user.user_id
        assert is_new is False
        
        # Verify OAuth identity was created
        from sqlalchemy import select
        from pdf_ai_agent.config.database.models.model_auth import OAuthIdentityModel
        
        result = await db_session.execute(
            select(OAuthIdentityModel).where(
                OAuthIdentityModel.user_id == user.user_id
            )
        )
        oauth_identity = result.scalar_one_or_none()
        assert oauth_identity is not None
        assert oauth_identity.provider_subject == "67890"
    
    @pytest.mark.asyncio
    async def test_handle_oauth_user_create_new(self, db_session):
        """Test OAuth user handling - create new user."""
        service = AuthService(db_session=db_session)
        
        # Handle OAuth user (should create new user)
        result_user, is_new = await service.handle_oauth_user(
            provider="google",
            provider_subject="new12345",
            provider_email="newuser@example.com",
            provider_name="New User",
            avatar_url="https://example.com/avatar.jpg",
        )
        
        assert is_new is True
        assert result_user.email == "newuser@example.com"
        assert result_user.full_name == "New User"
        assert result_user.avatar_url == "https://example.com/avatar.jpg"
        assert result_user.email_verified is True
        
        # Verify OAuth identity was created
        from sqlalchemy import select
        from pdf_ai_agent.config.database.models.model_auth import OAuthIdentityModel
        
        result = await db_session.execute(
            select(OAuthIdentityModel).where(
                OAuthIdentityModel.user_id == result_user.user_id
            )
        )
        oauth_identity = result.scalar_one_or_none()
        assert oauth_identity is not None
        assert oauth_identity.provider_subject == "new12345"
    
    def test_generate_username_from_email(self, db_session):
        """Test username generation from email."""
        service = AuthService(db_session=db_session)
        
        username1 = service._generate_username_from_email("john.doe@example.com")
        assert username1 == "john_doe"
        
        username2 = service._generate_username_from_email("test+tag@example.com")
        assert "test" in username2
        
        username3 = service._generate_username_from_email("verylongemailaddressname@example.com")
        assert len(username3) <= 20
