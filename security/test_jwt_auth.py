"""
Comprehensive tests for JWT authentication module.
"""
import time
from datetime import datetime, timedelta, timezone
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend

from security import (
    KeyManager,
    TokenOperations,
    TokenExpiredError,
    InvalidSignatureError,
    InvalidIssuerError,
    InvalidAudienceError,
    MalformedTokenError,
    UnknownKidError,
    InvalidAlgorithmError,
)


# Test fixtures
@pytest.fixture
def test_keys():
    """Generate test ECDSA key pairs."""
    # Generate first key pair
    private_key_1 = ec.generate_private_key(ec.SECP256R1(), default_backend())
    public_key_1 = private_key_1.public_key()
    
    private_pem_1 = private_key_1.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    ).decode('utf-8')
    
    public_pem_1 = public_key_1.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    ).decode('utf-8')
    
    # Generate second key pair for rotation testing
    private_key_2 = ec.generate_private_key(ec.SECP256R1(), default_backend())
    public_key_2 = private_key_2.public_key()
    
    private_pem_2 = private_key_2.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    ).decode('utf-8')
    
    public_pem_2 = public_key_2.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    ).decode('utf-8')
    
    return {
        "key1": {
            "kid": "test-key-1",
            "private": private_pem_1,
            "public": public_pem_1,
        },
        "key2": {
            "kid": "test-key-2",
            "private": private_pem_2,
            "public": public_pem_2,
        }
    }


@pytest.fixture
def key_manager(test_keys):
    """Create a test key manager."""
    keyset = {
        test_keys["key1"]["kid"]: test_keys["key1"]["public"],
        test_keys["key2"]["kid"]: test_keys["key2"]["public"],
    }
    return KeyManager(
        active_kid=test_keys["key1"]["kid"],
        private_key_pem=test_keys["key1"]["private"],
        keyset=keyset
    )


@pytest.fixture
def token_ops(key_manager):
    """Create token operations instance."""
    return TokenOperations(
        key_manager=key_manager,
        issuer="test-issuer",
        audience="test-audience",
        leeway=0
    )


class TestKeyManager:
    """Tests for KeyManager class."""
    
    def test_key_manager_initialization(self, test_keys):
        """Test key manager initializes correctly."""
        keyset = {test_keys["key1"]["kid"]: test_keys["key1"]["public"]}
        km = KeyManager(
            active_kid=test_keys["key1"]["kid"],
            private_key_pem=test_keys["key1"]["private"],
            keyset=keyset
        )
        assert km.active_kid == test_keys["key1"]["kid"]
        assert km.get_private_key() is not None
    
    def test_get_public_key_success(self, key_manager, test_keys):
        """Test retrieving public key by kid."""
        public_key = key_manager.get_public_key(test_keys["key1"]["kid"])
        assert public_key is not None
    
    def test_get_public_key_unknown_kid(self, key_manager):
        """Test error on unknown kid."""
        with pytest.raises(UnknownKidError):
            key_manager.get_public_key("unknown-kid")
    
    def test_key_rotation_support(self, key_manager, test_keys):
        """Test that multiple keys can be stored for rotation."""
        # Both keys should be accessible
        key1 = key_manager.get_public_key(test_keys["key1"]["kid"])
        key2 = key_manager.get_public_key(test_keys["key2"]["kid"])
        assert key1 is not None
        assert key2 is not None


class TestTokenGeneration:
    """Tests for token generation."""
    
    def test_generate_basic_token(self, token_ops):
        """Test generating a basic token with required claims."""
        token = token_ops.generate_access_token(user_id="user123")
        assert token is not None
        assert isinstance(token, str)
        
        # Decode without verification to check structure
        payload = jwt.decode(token, options={"verify_signature": False})
        assert payload["sub"] == "user123"
        assert "iat" in payload
        assert "exp" in payload
        assert "iss" in payload
        assert "aud" in payload
    
    def test_generate_token_with_optional_claims(self, token_ops):
        """Test generating token with optional claims."""
        token = token_ops.generate_access_token(
            user_id="user123",
            email="user@example.com",
            fullname="Test User"
        )
        
        payload = jwt.decode(token, options={"verify_signature": False})
        assert payload["email"] == "user@example.com"
        assert payload["fullname"] == "Test User"
    
    def test_token_includes_kid_in_header(self, token_ops, key_manager):
        """Test that token header includes kid."""
        token = token_ops.generate_access_token(user_id="user123")
        header = jwt.get_unverified_header(token)
        assert header["kid"] == key_manager.active_kid
        assert header["typ"] == "JWT"
        assert header["alg"] == "ES256"
    
    def test_custom_expiration(self, token_ops):
        """Test custom expiration time."""
        token = token_ops.generate_access_token(user_id="user123", expires_in=7200)
        payload = jwt.decode(token, options={"verify_signature": False})
        
        iat = datetime.fromtimestamp(payload["iat"], tz=timezone.utc)
        exp = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
        
        # Check that expiration is approximately 2 hours from issued time
        delta = (exp - iat).total_seconds()
        assert 7195 <= delta <= 7205  # Allow small variance


class TestTokenVerification:
    """Tests for token verification."""
    
    def test_verify_valid_token(self, token_ops):
        """Test happy path: mint and verify valid token."""
        token = token_ops.generate_access_token(user_id="user123")
        payload = token_ops.verify_and_decode_token(token)
        
        assert payload["sub"] == "user123"
        assert payload["iss"] == "test-issuer"
        assert payload["aud"] == "test-audience"
    
    def test_verify_expired_token(self, token_ops):
        """Test that expired tokens are rejected."""
        # Generate token that expires immediately
        token = token_ops.generate_access_token(user_id="user123", expires_in=1)
        
        # Wait for token to expire
        time.sleep(2)
        
        with pytest.raises(TokenExpiredError):
            token_ops.verify_and_decode_token(token)
    
    def test_verify_tampered_signature(self, token_ops):
        """Test that tokens with tampered signatures are rejected."""
        token = token_ops.generate_access_token(user_id="user123")
        
        # Tamper with the token
        parts = token.split('.')
        tampered_token = f"{parts[0]}.{parts[1]}.{'x' * len(parts[2])}"
        
        with pytest.raises(InvalidSignatureError):
            token_ops.verify_and_decode_token(tampered_token)
    
    def test_verify_tampered_payload(self, token_ops):
        """Test that tokens with tampered payloads are rejected."""
        token = token_ops.generate_access_token(user_id="user123")
        
        # Tamper with payload
        parts = token.split('.')
        # Decode, modify, re-encode payload
        import base64
        import json
        # Add proper padding
        padding = (4 - len(parts[1]) % 4) % 4
        payload = json.loads(base64.urlsafe_b64decode(parts[1] + '=' * padding))
        payload["sub"] = "hacker"
        tampered_payload = base64.urlsafe_b64encode(
            json.dumps(payload).encode()
        ).decode().rstrip('=')
        tampered_token = f"{parts[0]}.{tampered_payload}.{parts[2]}"
        
        with pytest.raises(InvalidSignatureError):
            token_ops.verify_and_decode_token(tampered_token)
    
    def test_verify_wrong_issuer(self, key_manager):
        """Test that tokens with wrong issuer are rejected."""
        # Create token with different issuer
        wrong_ops = TokenOperations(
            key_manager=key_manager,
            issuer="wrong-issuer",
            audience="test-audience"
        )
        token = wrong_ops.generate_access_token(user_id="user123")
        
        # Try to verify with correct issuer
        correct_ops = TokenOperations(
            key_manager=key_manager,
            issuer="test-issuer",
            audience="test-audience"
        )
        
        with pytest.raises(InvalidIssuerError):
            correct_ops.verify_and_decode_token(token)
    
    def test_verify_wrong_audience(self, key_manager):
        """Test that tokens with wrong audience are rejected."""
        # Create token with different audience
        wrong_ops = TokenOperations(
            key_manager=key_manager,
            issuer="test-issuer",
            audience="wrong-audience"
        )
        token = wrong_ops.generate_access_token(user_id="user123")
        
        # Try to verify with correct audience
        correct_ops = TokenOperations(
            key_manager=key_manager,
            issuer="test-issuer",
            audience="test-audience"
        )
        
        with pytest.raises(InvalidAudienceError):
            correct_ops.verify_and_decode_token(token)
    
    def test_verify_unknown_kid(self, test_keys):
        """Test that tokens with unknown kid are rejected."""
        # Create key manager with only one key
        single_keyset = {test_keys["key1"]["kid"]: test_keys["key1"]["public"]}
        km1 = KeyManager(
            active_kid=test_keys["key1"]["kid"],
            private_key_pem=test_keys["key1"]["private"],
            keyset=single_keyset
        )
        
        # Create token with second key
        km2 = KeyManager(
            active_kid=test_keys["key2"]["kid"],
            private_key_pem=test_keys["key2"]["private"],
            keyset={test_keys["key2"]["kid"]: test_keys["key2"]["public"]}
        )
        
        ops2 = TokenOperations(key_manager=km2)
        token = ops2.generate_access_token(user_id="user123")
        
        # Try to verify with first key manager (doesn't have key2)
        ops1 = TokenOperations(key_manager=km1)
        
        with pytest.raises(UnknownKidError):
            ops1.verify_and_decode_token(token)
    
    def test_verify_malformed_token(self, token_ops):
        """Test that malformed tokens are rejected."""
        with pytest.raises(MalformedTokenError):
            token_ops.verify_and_decode_token("not.a.valid.token")
    
    def test_reject_non_es256_algorithm(self, token_ops, key_manager):
        """Test that non-ES256 algorithms are rejected."""
        # Create a token with HS256 (will fail signature but should fail on alg first)
        token = jwt.encode(
            {"sub": "user123"},
            "secret",
            algorithm="HS256",
            headers={"kid": key_manager.active_kid}
        )
        
        with pytest.raises(InvalidAlgorithmError):
            token_ops.verify_and_decode_token(token)


class TestLeewayBehavior:
    """Tests for clock skew leeway."""
    
    def test_leeway_allows_expired_within_window(self, key_manager):
        """Test that leeway allows expired tokens within window."""
        # Create ops with 10 second leeway
        ops = TokenOperations(key_manager=key_manager, leeway=10)
        
        # Create token that expires in 1 second
        token = ops.generate_access_token(user_id="user123", expires_in=1)
        
        # Wait for token to "expire"
        time.sleep(2)
        
        # Should still verify due to leeway
        payload = ops.verify_and_decode_token(token)
        assert payload["sub"] == "user123"
    
    def test_leeway_rejects_expired_outside_window(self, key_manager):
        """Test that leeway doesn't allow tokens expired beyond window."""
        # Create ops with 2 second leeway
        ops = TokenOperations(key_manager=key_manager, leeway=2)
        
        # Create token that expires in 1 second
        token = ops.generate_access_token(user_id="user123", expires_in=1)
        
        # Wait beyond leeway window
        time.sleep(4)
        
        # Should fail verification
        with pytest.raises(TokenExpiredError):
            ops.verify_and_decode_token(token)


class TestUnsafeDecode:
    """Tests for unsafe token decoding."""
    
    def test_decode_without_verification(self, token_ops):
        """Test decoding token without verification."""
        token = token_ops.generate_access_token(user_id="user123")
        payload = token_ops.decode_token_unsafe(token)
        
        assert payload["sub"] == "user123"
    
    def test_decode_expired_token_without_verification(self, token_ops):
        """Test that unsafe decode works on expired tokens."""
        token = token_ops.generate_access_token(user_id="user123", expires_in=1)
        time.sleep(2)
        
        # Should decode successfully even though expired
        payload = token_ops.decode_token_unsafe(token)
        assert payload["sub"] == "user123"
    
    def test_decode_malformed_token_fails(self, token_ops):
        """Test that unsafe decode still fails on malformed tokens."""
        with pytest.raises(MalformedTokenError):
            token_ops.decode_token_unsafe("not.a.token")


class TestKeyRotation:
    """Tests for key rotation scenarios."""
    
    def test_verify_old_token_after_rotation(self, test_keys):
        """Test that old tokens can still be verified after key rotation."""
        # Start with key1 active
        keyset = {
            test_keys["key1"]["kid"]: test_keys["key1"]["public"],
            test_keys["key2"]["kid"]: test_keys["key2"]["public"],
        }
        km1 = KeyManager(
            active_kid=test_keys["key1"]["kid"],
            private_key_pem=test_keys["key1"]["private"],
            keyset=keyset
        )
        ops1 = TokenOperations(key_manager=km1)
        
        # Generate token with key1
        old_token = ops1.generate_access_token(user_id="user123")
        
        # "Rotate" to key2 (create new key manager with key2 active)
        km2 = KeyManager(
            active_kid=test_keys["key2"]["kid"],
            private_key_pem=test_keys["key2"]["private"],
            keyset=keyset  # Still includes key1 for verification
        )
        ops2 = TokenOperations(key_manager=km2)
        
        # Old token should still verify
        payload = ops2.verify_and_decode_token(old_token)
        assert payload["sub"] == "user123"
        
        # New tokens use key2
        new_token = ops2.generate_access_token(user_id="user456")
        header = jwt.get_unverified_header(new_token)
        assert header["kid"] == test_keys["key2"]["kid"]


class TestMissingClaims:
    """Tests for missing required claims."""
    
    def test_token_missing_sub(self, key_manager):
        """Test that tokens missing 'sub' are rejected."""
        # Create token without sub claim
        private_key = key_manager.get_private_key()
        token = jwt.encode(
            {"iat": datetime.now(timezone.utc), "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
            private_key,
            algorithm="ES256",
            headers={"kid": key_manager.active_kid}
        )
        
        ops = TokenOperations(key_manager=key_manager)
        with pytest.raises(MalformedTokenError):
            ops.verify_and_decode_token(token)
    
    def test_token_missing_kid_in_header(self, key_manager):
        """Test that tokens missing 'kid' in header are rejected."""
        # Create token without kid in header
        private_key = key_manager.get_private_key()
        token = jwt.encode(
            {
                "sub": "user123",
                "iat": datetime.now(timezone.utc),
                "exp": datetime.now(timezone.utc) + timedelta(hours=1)
            },
            private_key,
            algorithm="ES256"
        )
        
        ops = TokenOperations(key_manager=key_manager)
        with pytest.raises(MalformedTokenError):
            ops.verify_and_decode_token(token)
