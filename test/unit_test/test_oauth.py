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
