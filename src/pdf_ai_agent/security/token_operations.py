"""
JWT token operations for generation, verification, and decoding.
"""
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, Any
import jwt

from .exceptions import (
    TokenExpiredError,
    InvalidSignatureError,
    InvalidIssuerError,
    InvalidAudienceError,
    MalformedTokenError,
    InvalidAlgorithmError,
)
from .key_manager import KeyManager


class TokenOperations:
    """
    Handles JWT token generation and verification using ES256.
    """
    
    ALGORITHM = "ES256"
    ALLOWED_ALGORITHMS = ["ES256"]
    
    def __init__(
        self,
        key_manager: KeyManager,
        issuer: Optional[str] = None,
        audience: Optional[str] = None,
        leeway: int = 0,
    ):
        """
        Initialize token operations.
        
        Args:
            key_manager: KeyManager instance for key operations
            issuer: Optional issuer (iss claim) to validate
            audience: Optional audience (aud claim) to validate
            leeway: Leeway in seconds for clock skew (default: 0)
        """
        self.key_manager = key_manager
        self.issuer = issuer
        self.audience = audience
        self.leeway = leeway
    
    def generate_access_token(
        self,
        user_id: str,
        expires_in: int = 3600,
        email: Optional[str] = None,
        fullname: Optional[str] = None,
        additional_claims: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Generate a JWT access token signed with ES256.
        
        Args:
            user_id: User ID to include as 'sub' claim
            expires_in: Token expiration time in seconds (default: 3600)
            email: Optional email address to include
            fullname: Optional full name to include
            additional_claims: Optional additional claims to include
            
        Returns:
            Signed JWT token string
        """
        now = datetime.now(timezone.utc)
        
        # Build claims
        claims = {
            "sub": user_id,
            "iat": now,
            "exp": now + timedelta(seconds=expires_in),
        }
        
        # Add optional claims
        if self.issuer:
            claims["iss"] = self.issuer
        if self.audience:
            claims["aud"] = self.audience
        if email:
            claims["email"] = email
        if fullname:
            claims["fullname"] = fullname
        if additional_claims:
            claims.update(additional_claims)
        
        # Get private key for signing
        private_key = self.key_manager.get_private_key()
        
        # Sign token with kid in header
        token = jwt.encode(
            claims,
            private_key,
            algorithm=self.ALGORITHM,
            headers={"kid": self.key_manager.active_kid, "typ": "JWT"},
        )
        
        return token
    
    def verify_and_decode_token(self, token: str) -> Dict[str, Any]:
        """
        Verify and decode a JWT token with full validation.
        
        Args:
            token: JWT token string to verify
            
        Returns:
            Decoded token payload as dictionary
            
        Raises:
            TokenExpiredError: If token has expired
            InvalidSignatureError: If token signature is invalid
            InvalidIssuerError: If token issuer is invalid
            InvalidAudienceError: If token audience is invalid
            MalformedTokenError: If token is malformed or missing claims
            InvalidAlgorithmError: If token uses invalid algorithm
        """
        try:
            # First, decode header without verification to get kid
            unverified_header = jwt.get_unverified_header(token)
            
            # Check algorithm
            alg = unverified_header.get("alg")
            if alg not in self.ALLOWED_ALGORITHMS:
                raise InvalidAlgorithmError(
                    f"Invalid algorithm: {alg}. Only {self.ALLOWED_ALGORITHMS} allowed."
                )
            
            # Get kid from header
            kid = unverified_header.get("kid")
            if not kid:
                raise MalformedTokenError("Token missing 'kid' in header")
            
            # Get public key for verification
            public_key = self.key_manager.get_public_key(kid)
            
            # Build verification options
            options = {
                "verify_signature": True,
                "verify_exp": True,
                "verify_iat": True,
                "require": ["sub", "exp", "iat"],
            }
            
            # Add issuer/audience requirements if configured
            if self.issuer:
                options["verify_iss"] = True
            if self.audience:
                options["verify_aud"] = True
            
            # Verify and decode token
            payload = jwt.decode(
                token,
                public_key,
                algorithms=self.ALLOWED_ALGORITHMS,
                issuer=self.issuer,
                audience=self.audience,
                leeway=self.leeway,
                options=options,
            )
            
            return payload
            
        except jwt.ExpiredSignatureError as e:
            raise TokenExpiredError("Token has expired") from e
        except jwt.InvalidSignatureError as e:
            raise InvalidSignatureError("Invalid token signature") from e
        except jwt.InvalidIssuerError as e:
            raise InvalidIssuerError("Invalid token issuer") from e
        except jwt.InvalidAudienceError as e:
            raise InvalidAudienceError("Invalid token audience") from e
        except jwt.DecodeError as e:
            raise MalformedTokenError("Token is malformed") from e
        except jwt.MissingRequiredClaimError as e:
            raise MalformedTokenError(f"Token missing required claim: {e}") from e
        except jwt.InvalidTokenError as e:
            raise MalformedTokenError(f"Invalid token: {e}") from e
    
    def decode_token_unsafe(self, token: str) -> Dict[str, Any]:
        """
        Decode a JWT token WITHOUT verification.
        
        WARNING: This method does NOT verify the token signature or claims.
        Use only for debugging and troubleshooting purposes.
        
        Args:
            token: JWT token string to decode
            
        Returns:
            Decoded token payload as dictionary
            
        Raises:
            MalformedTokenError: If token cannot be decoded
        """
        try:
            payload = jwt.decode(
                token,
                options={"verify_signature": False},
            )
            return payload
        except jwt.DecodeError as e:
            raise MalformedTokenError("Token is malformed") from e
