"""OAuth configuration from environment variables."""
import os
from functools import lru_cache
from pydantic import BaseModel, Field
from typing import List


class OAuthConfig(BaseModel):
    """OAuth configuration from environment variables."""
    
    google_client_id: str = Field(..., description="Google OAuth client ID")
    google_client_secret: str = Field(..., description="Google OAuth client secret")
    google_auth_endpoint: str = Field(
        default="https://accounts.google.com/o/oauth2/v2/auth",
        description="Google OAuth authorization endpoint"
    )
    google_token_endpoint: str = Field(
        default="https://oauth2.googleapis.com/token",
        description="Google OAuth token endpoint"
    )
    google_redirect_uri: str = Field(..., description="Google OAuth redirect URI")
    google_scopes: str = Field(
        default="openid email profile",
        description="Google OAuth scopes"
    )
    oauth_allowed_redirect_to_prefixes: List[str] = Field(
        default=["/", "/app", "/settings"],
        description="Allowed redirect_to path prefixes"
    )
    oauth_enabled: bool = Field(
        default=True,
        description="Whether OAuth is enabled"
    )
    
    @classmethod
    def from_env(cls) -> "OAuthConfig":
        """
        Load OAuth configuration from environment variables.
        
        Returns:
            OAuthConfig instance
        """
        google_client_id = os.getenv("GOOGLE_CLIENT_ID", "")
        google_client_secret = os.getenv("GOOGLE_CLIENT_SECRET", "")
        google_auth_endpoint = os.getenv(
            "GOOGLE_AUTH_ENDPOINT",
            "https://accounts.google.com/o/oauth2/v2/auth"
        )
        google_token_endpoint = os.getenv(
            "GOOGLE_TOKEN_ENDPOINT",
            "https://oauth2.googleapis.com/token"
        )
        google_redirect_uri = os.getenv("GOOGLE_REDIRECT_URI", "")
        google_scopes = os.getenv("GOOGLE_SCOPES", "openid email profile")
        
        # Parse allowed redirect_to prefixes
        allowed_prefixes_str = os.getenv(
            "OAUTH_ALLOWED_REDIRECT_TO_PREFIXES",
            "/,/app,/settings"
        )
        oauth_allowed_redirect_to_prefixes = [
            prefix.strip() for prefix in allowed_prefixes_str.split(",")
        ]
        
        oauth_enabled = os.getenv("OAUTH_ENABLED", "true").lower() == "true"
        
        return cls(
            google_client_id=google_client_id,
            google_client_secret=google_client_secret,
            google_auth_endpoint=google_auth_endpoint,
            google_token_endpoint=google_token_endpoint,
            google_redirect_uri=google_redirect_uri,
            google_scopes=google_scopes,
            oauth_allowed_redirect_to_prefixes=oauth_allowed_redirect_to_prefixes,
            oauth_enabled=oauth_enabled,
        )


@lru_cache()
def get_oauth_config() -> OAuthConfig:
    """
    Get cached OAuth configuration.
    
    Returns:
        OAuthConfig instance
    """
    return OAuthConfig.from_env()
