"""Application configuration from YAML file."""
import os
import yaml
from functools import lru_cache
from pydantic import BaseModel, Field
from typing import Optional


class AppConfig(BaseModel):
    """Application configuration from config.yaml."""
    
    oauth_state_ttl_seconds: int = Field(
        default=600,
        description="OAuth state TTL in seconds"
    )
    oauth_pkce_enabled: bool = Field(
        default=True,
        description="Whether OAuth PKCE is enabled"
    )
    
    @classmethod
    def from_yaml(cls, config_path: Optional[str] = None) -> "AppConfig":
        """
        Load application configuration from YAML file.
        
        Args:
            config_path: Path to config.yaml file. If None, uses CONFIG_PATH env var
                        or defaults to ./config.yaml
        
        Returns:
            AppConfig instance
        """
        if config_path is None:
            config_path = os.getenv("CONFIG_PATH", "config.yaml")
        
        # If file doesn't exist, return default config
        if not os.path.exists(config_path):
            return cls()
        
        try:
            with open(config_path, 'r') as f:
                config_data = yaml.safe_load(f) or {}
        except Exception:
            # If error reading file, return default config
            return cls()
        
        oauth_state_ttl_seconds = config_data.get("OAUTH_STATE_TTL_SECONDS", 600)
        oauth_pkce_enabled = config_data.get("OAUTH_PKCE_ENABLED", True)
        
        return cls(
            oauth_state_ttl_seconds=oauth_state_ttl_seconds,
            oauth_pkce_enabled=oauth_pkce_enabled,
        )


@lru_cache()
def get_app_config() -> AppConfig:
    """
    Get cached application configuration.
    
    Returns:
        AppConfig instance
    """
    return AppConfig.from_yaml()
