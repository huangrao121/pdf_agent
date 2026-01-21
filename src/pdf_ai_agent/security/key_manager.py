"""
Key manager for handling JWT signing and verification keys with rotation support.
"""
import os
from typing import Dict, Optional
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.backends import default_backend

from .exceptions import UnknownKidError

from functools import lru_cache

from pdf_ai_agent.config.jwt_config import JWTConfig

class KeyManager:
    """
    Manages ECDSA keys for JWT signing and verification.
    
    Supports key rotation by maintaining:
    - An active key ID (kid) for signing
    - A keyset mapping kid -> public key for verification
    """
    
    def __init__(self, config: JWTConfig):
        """
        Initialize the key manager.
        
        Args:
            active_kid: The key ID to use for signing tokens
            private_key_pem: PEM-encoded private key for the active kid
            keyset: Dictionary mapping kid -> public_key_pem for verification
        """
        self.active_kid = config.active_kid
        self._private_key_pem = config.jwt_private_key
        self.keyset = config.key_set
        
        # Load private key for signing
        self._private_key = serialization.load_pem_private_key(
            self._private_key_pem.encode('utf-8'),
            password=None,
            backend=default_backend()
        )
        
        # Load public keys for verification
        self._public_keys: Dict[str, ec.EllipticCurvePublicKey] = {}
        for kid, pub_key_pem in self.keyset.items():
            self._public_keys[kid] = serialization.load_pem_public_key(
                pub_key_pem.encode('utf-8'),
                backend=default_backend()
            )
    
    def get_private_key(self) -> ec.EllipticCurvePrivateKey:
        """Get the private key for signing."""
        return self._private_key
    
    def get_public_key(self, kid: str) -> ec.EllipticCurvePublicKey:
        """
        Get the public key for a given key ID.
        
        Args:
            kid: The key ID to look up
            
        Returns:
            The public key for the given kid
            
        Raises:
            UnknownKidError: If the kid is not in the keyset
        """
        if kid not in self._public_keys:
            raise UnknownKidError(f"Unknown key ID: {kid}")
        return self._public_keys[kid]
    
    # @classmethod
    # def from_env(cls) -> "KeyManager":
    #     """
    #     Load key manager configuration from environment variables.
        
    #     Expected environment variables:
    #     - JWT_ACTIVE_KID: The active key ID for signing
    #     - JWT_PRIVATE_KEY: PEM-encoded private key for signing
    #     - JWT_KEYSET: JSON string mapping kid -> public_key_pem
        
    #     Example JWT_KEYSET:
    #     {
    #         "key-2024-01": "-----BEGIN PUBLIC KEY-----\\n...\\n-----END PUBLIC KEY-----",
    #         "key-2024-02": "-----BEGIN PUBLIC KEY-----\\n...\\n-----END PUBLIC KEY-----"
    #     }
        
    #     Returns:
    #         KeyManager instance configured from environment
    #     """
    #     import json
        
    #     active_kid = os.getenv("JWT_ACTIVE_KID")
    #     private_key_pem = os.getenv("JWT_PRIVATE_KEY")
    #     keyset_json = os.getenv("JWT_KEYSET")
        
    #     if not active_kid:
    #         raise ValueError("JWT_ACTIVE_KID environment variable is required")
    #     if not private_key_pem:
    #         raise ValueError("JWT_PRIVATE_KEY environment variable is required")
    #     if not keyset_json:
    #         raise ValueError("JWT_KEYSET environment variable is required")
        
    #     # Parse keyset JSON
    #     keyset = json.loads(keyset_json)
        
    #     # Ensure active_kid is in keyset
    #     if active_kid not in keyset:
    #         raise ValueError(f"Active kid '{active_kid}' not found in keyset")
        
    #     return cls(active_kid, private_key_pem, keyset)

@lru_cache()
def get_key_manager() -> KeyManager:
    """
    Get a cached KeyManager instance loaded from environment variables.
    """
    config = JWTConfig.from_env()
    return KeyManager(config)