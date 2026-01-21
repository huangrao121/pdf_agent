"""
Tests for OAuth authorization endpoint.
"""
import pytest
import os
from unittest.mock import patch, MagicMock
from fastapi import status
from fastapi.testclient import TestClient
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
    """Tests for OAuth authorization endpoint."""
    
    @pytest.fixture
    def mock_env_vars(self):
        """Mock environment variables for OAuth."""
        with patch.dict(os.environ, {
            "GOOGLE_CLIENT_ID": "test_client_id",
            "GOOGLE_CLIENT_SECRET": "test_client_secret",
            "GOOGLE_REDIRECT_URI": "http://localhost:8000/callback",
            "GOOGLE_SCOPES": "openid email profile",
            "OAUTH_ENABLED": "true",
            "OAUTH_ALLOWED_REDIRECT_TO_PREFIXES": "/,/app,/settings",
        }):
            # Clear the lru_cache to ensure new config is loaded
            from pdf_ai_agent.config.oauth_config import get_oauth_config
            get_oauth_config.cache_clear()
            yield
            get_oauth_config.cache_clear()
    
    @pytest.fixture
    def app(self, db_session, mock_env_vars):
        """Create FastAPI test app."""
        from main import create_app
        from pdf_ai_agent.config.database.init_database import get_db_session
        
        app = create_app()
        
        # Override the get_db_session dependency
        async def override_get_db_session():
            yield db_session
        
        app.dependency_overrides[get_db_session] = override_get_db_session
        return app
    
    def test_oauth_authorize_success(self, app):
        """Test successful OAuth authorization."""
        client = TestClient(app)
        
        response = client.post(
            "/api/auth/oauth/google/authorize",
            json={"redirect_to": "/app"}
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        
        assert data["status"] == "ok"
        assert "data" in data
        assert "authorization_url" in data["data"]
        assert "provider" in data["data"]
        assert "state" in data["data"]
        
        assert data["data"]["provider"] == "google"
        assert data["data"]["state"].startswith("st_")
        assert "accounts.google.com" in data["data"]["authorization_url"]
        
        # Check cookies
        assert "oauth_state" in response.cookies
        assert "oauth_pkce_verifier" in response.cookies
        assert "oauth_redirect_to" in response.cookies
    
    def test_oauth_authorize_invalid_redirect_to(self, app):
        """Test OAuth authorization with invalid redirect_to."""
        client = TestClient(app)
        
        response = client.post(
            "/api/auth/oauth/google/authorize",
            json={"redirect_to": "https://evil.com"}
        )
        
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        data = response.json()
        
        assert data["status"] == "error"
        assert data["error_code"] == "VALIDATION_FAILED"
    
    def test_oauth_authorize_disabled(self, db_session):
        """Test OAuth authorization when OAuth is disabled."""
        with patch.dict(os.environ, {
            "GOOGLE_CLIENT_ID": "test_client_id",
            "GOOGLE_CLIENT_SECRET": "test_client_secret",
            "GOOGLE_REDIRECT_URI": "http://localhost:8000/callback",
            "OAUTH_ENABLED": "false",
        }):
            from pdf_ai_agent.config.oauth_config import get_oauth_config
            get_oauth_config.cache_clear()
            
            from main import create_app
            from pdf_ai_agent.config.database.init_database import get_db_session
            
            app = create_app()
            
            async def override_get_db_session():
                yield db_session
            
            app.dependency_overrides[get_db_session] = override_get_db_session
            
            client = TestClient(app)
            response = client.post(
                "/api/auth/oauth/google/authorize",
                json={"redirect_to": "/app"}
            )
            
            assert response.status_code == status.HTTP_403_FORBIDDEN
            data = response.json()
            
            assert data["status"] == "error"
            assert data["error_code"] == "OAUTH_DISABLED"
            
            get_oauth_config.cache_clear()
